import base64, requests, json
from odoo import _, api, fields, models, tools
import logging
from datetime import datetime
from odoo.tools import pytz

_logger = logging.getLogger(__name__)


class L10nEcEdiDocument(models.Model):

    _inherit = 'l10nec.edi.document'

    def action_send_document(self):
        """Send document to invoixo"""
        self.ensure_one()

        url = self.company_id.invoixo_url + "/v1.0/edoc/" + self.name
        payload = json.dumps({
            'xml': self.xml_content,
            'pwd': self.company_id.invoixo_signature_password,
        })

        headers = {
            'Content-Type': 'application/json'
        }

        res = requests.post(url, payload, headers=headers)

        response = res.json()

        if response["status"] == "success":
            self.state = "sent"



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
        url = self.company_id.invoixo_url + "/v1.0/edoc/ride/pdf/" + self.name
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new'
        }
