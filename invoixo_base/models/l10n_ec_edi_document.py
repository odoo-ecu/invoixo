import base64, requests, json
from requests.exceptions import ConnectionError as RConnectionError
from odoo import _, api, fields, models, tools
import logging
from datetime import datetime
from odoo.tools import pytz
from odoo.tools.zeep import Client
from odoo.tools.zeep.exceptions import Error as ZeepError

_logger = logging.getLogger(__name__)

TESTING_URL = {
    'reception': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
    'authorization': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
}

PRODUCTION_URL = {
    'reception': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
    'authorization': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
}

DEFAULT_TIMEOUT_WS = 20


class L10nEcEdiDocument(models.Model):

    _inherit = 'l10nec.edi.document'

    def _get_response(self, mode, **kwargs):
        """
        SRI SOAP
        """
        self.ensure_one()
        if self.company_id.l10n_ec_production_env:
            wsdl_url = PRODUCTION_URL.get(mode)
        else:
            wsdl_url = TESTING_URL.get(mode)

        errors, warnings = [], []
        response = None
        try:
            client = Client(wsdl=wsdl_url, timeout=DEFAULT_TIMEOUT_WS)
            if mode == "reception":
                response = client.service.validarComprobante(**kwargs)
            elif mode == "authorization":
                response = client.service.autorizacionComprobante(**kwargs)
            if not response:
                errors.append(_("No response received."))
        except ZeepError as e:
            errors.append(_("The SRI service failed with the following error: %s", e))
        except RConnectionError as e:
            warnings.append(_("The SRI service failed with the following message: %s", e))
        return response, errors, warnings

    def get_auth(self):
        """
        SRI interaction: Get authorization
        """
        auth_state, auth_num, auth_date = None, None, None

        response, zeep_errors, zeep_warnings = self._get_response(
            "authorization",
            claveAccesoComprobante=self.name
        )
        if zeep_errors:
            return auth_state, auth_num, auth_date, zeep_errors, zeep_warnings
        try:
            response_auth_list = response.autorizaciones and response.autorizaciones.autorizacion or []
        except AttributeError as err:
            return auth_state, auth_num, auth_date, [_("SRI response unexpected: %s", err)], zeep_warnings

        errors = []
        if not isinstance(response_auth_list, list):
            response_auth_list = [response_auth_list]

        for doc in response_auth_list:
            auth_state = doc.estado
            if doc.estado == "AUTORIZADO":
                auth_num = doc.numeroAutorizacion
                auth_date = doc.fechaAutorizacion
            else:
                messages = doc.mensajes
                if messages:
                    messages_list = messages.mensaje
                    if not isinstance(messages_list, list):
                        messages_list = messages
                    for msg in messages_list:
                        errors.append(' - '.join(
                            filter(None, [msg.identificador, msg.informacionAdicional, msg.mensaje, msg.tipo])
                        ))
        return auth_state, auth_num, auth_date, errors, zeep_warnings

    def _create_authorization_file(self, move, xml_string, authorization_number, authorization_date):
        xml_values = {
            'xml_file_content': Markup(xml_string[xml_string.find('?>') + 2:]),  # remove header to embed sent xml
            'mode': 'PRODUCCION' if move.company_id.l10n_ec_production_env else 'PRUEBAS',
            'authorization_number': authorization_number,
            'authorization_date': authorization_date.strftime(DTF),
        }
        xml_response = self.env['ir.qweb']._render('l10n_ec_edi.authorization_template', xml_values)
        xml_response = cleanup_xml_node(xml_response)
        return etree.tostring(xml_response, encoding='unicode')

    def send_document(self):
        # === DEMO ENVIRONMENT REPONSE ===
        # if self.company_id._l10n_ec_is_demo_environment():
        #     return self._l10n_ec_generate_demo_xml_attachment(self, xml_string)

        self.ensure_one()

        # === STEP 1 ===
        errors, warnings = [], []
        if not self.authorization_date:
            # Submit the generated XML
            xml_signed = self.company_id.sudo().l10n_ec_edi_certificate_id._action_sign(self.xml_content)
            response, zeep_errors, warnings = self._get_response('reception', xml=xml_signed.encode())
            if zeep_errors:
                return zeep_errors, 'error', None
            try:
                response_state = response.estado
                response_checks = response.comprobantes and response.comprobantes.comprobante or []
            except AttributeError as err:
                return warnings or [_("SRI response unexpected: %s", err)], 'warning' if warnings else 'error', None

            # Parse govt's response for errors or response state
            if response_state == 'DEVUELTA':
                for check in response_checks:
                    for msg in check.mensajes.mensaje:
                        if msg.identificador != '43':  # 43 means Authorization number already registered
                            errors.append(' - '.join(
                                filter(None, [msg.identificador, msg.informacionAdicional, msg.mensaje, msg.tipo])
                            ))
            elif response_state != 'RECIBIDA':
                errors.append(_("SRI response state: %s", response_state))

            # If any errors have been found (other than those indicating already-authorized document)
            if errors:
                return errors, 'error', None

        # === STEP 2 ===
        # Get authorization status, store response & raise any errors
        attachment = False
        auth_state, auth_num, auth_date, auth_errors, auth_warnings = self.get_auth()
        errors.extend(auth_errors)
        warnings.extend(auth_warnings)
        if auth_num and auth_date:
            if self.name != auth_num:
                warnings.append(_("Authorization number %s does not match document's %s", auth_num, self.name))
            self.authorization_date = auth_date.replace(tzinfo=None)
            # attachment = self.env['ir.attachment'].create({
            #     'name': self.display_name + '.xml',
            #     'res_id': self.id,
            #     'res_model': self._name,
            #     'type': 'binary',
            #     'raw': self._authorization_file(self, xml_string, auth_num, auth_date),
            #     'mimetype': 'application/xml',
            #     'description': f"Ecuadorian electronic document generated for document {self.display_name}."
            # })
            self.message_post(
                body=_(
                    "Electronic document authorized.<br/><strong>Authorization num:</strong><br/>%s<br/><strong>Authorization date:</strong><br/>%s",
                    self.name, self.authorization_date
                ),
                # attachment_ids=attachment.ids,
            )
            self.state = "authorized"
        # elif self.state == 'to_cancel' and not self.company_id.l10n_ec_production_env:
            # In test environment, we act as if invoice had already been cancelled for the govt
            # warnings.append(_("Document with access key %s has been cancelled", self.name))
        elif not auth_num and auth_state == 'EN PROCESO':
            # No authorization number means the invoice was no authorized yet
            warnings.append(_("Document with access key %s received by government and pending authorization",
                              self.name))
        else:
            # SRI unexpected error
            errors.append(_("Document not authorized by SRI, please try again later"))

        # return errors or warnings, 'error' if errors else 'warning', attachment
        return errors or warnings, 'error' if errors else 'warning', False

    def action_send_document(self):
        """Send document to invoixo"""
        self.ensure_one()

        # url = self.company_id.invoixo_url + "/v1.0/edoc/" + self.name
        # payload = json.dumps({
        #     'xml': self.xml_content,
        #     'pwd': self.company_id.invoixo_signature_password,
        # })

        # headers = {
        #     'Content-Type': 'application/json'
        # }

        # res = requests.post(url, payload, headers=headers)

        # response = res.json()

        # if response["status"] == "success":
        #     self.state = "sent"

        xml_signed = self.company_id.sudo().l10n_ec_edi_certificate_id._action_sign(self.xml_content)
        _logger.info(xml_signed)
        errors, blocking_level, attachment = self.send_document()

        if blocking_level == 'error':
            body = "Error: " + "\n".join(errors)
            self.message_post(body=body)



    def action_check_document_status(self):
        """Check status of document in invoixo server"""
        self.ensure_one()
        if not self.name:
            return False
        url = self.company_id.invoixo_url + "/v1.0/edoc/" + self.name
        headers = {'Accept': 'application/json'}
        response = requests.get(url, headers=headers)
        _logger.info("Data was {} {}".format(response, response.content))
        try:
            data = json.loads(response.content.decode("utf-8"))
        except json.decoder.JSONDecodeError as error:
            _logger.error("Error in decoding JSON: {}, Reponse was: {}".format(error, response.content))
            return False
        msg = data.get("msg", "N/A")
        status = data.get("status", 'undefined')
        _logger.info("El mensaje es: {} para {}".format(msg, self.name))

        # if status_msg == 'DEVUELTA':
        #     self.state = "cancelled"

        # msg = ""

        # msgs = data.get("msgs", [])
        # for m in msgs:
        #     for k, v in m.items():
        #         msg += f'{k}: {v}\n'

        if status == 'error':
            self.state = 'error'

        if status == 'authorized':
            self.state = 'authorized'
            authorization_date = data.get("auth_date", "")

            user = self.env['res.users'].browse([2])
            tz = pytz.timezone(user.tz) or pytz.utc

            _logger.info("Authorization date {}".format(authorization_date))
            naive = datetime.strptime(authorization_date, "%Y-%m-%d %H:%M:%S")
            local_dt = tz.localize(naive, is_dst=None)
            auth_date = local_dt.astimezone(pytz.utc)
            self.authorization_date = auth_date.strftime("%Y-%m-%d %H:%M:%S")


        self.message_post(body=msg)



    def action_ride_download(self):
        self.ensure_one()
        url = self.company_id.invoixo_url + "/v1.0/edoc/ride/pdf/" + self.name
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new'
        }
