import base64, requests, json
from odoo import _, api, fields, models, tools
import logging

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

        requests.put(url, payload, headers=headers)

    def action_check_document_status(self):
        """Check status of document in invoixo server"""
        self.ensure_one()
        url = self.company_id.invoixo_url + "/v1.0/edoc/" + self.name
        headers = {'Accept': 'application/json'}
        response = requests.get(url, headers=headers)
        _logger.info("Data was {} {}".format(response, response.content))
        try:
            data = json.loads(response.content.decode("utf-8"))
        except json.decoder.JSONDecodeError as error:
            _logger.error("Error in decoding JSON: {}, Reponse was: {}".format(error, response.content))
            return False
        status_msg = data.get("status", "N/A")
        _logger.info("El status es: {}".format(status_msg))

        if status_msg == 'DEVUELTA':
            self.state = "cancelled"

        msg = ""

        msgs = data.get("msgs", [])
        for m in msgs:
            for k, v in m.items():
                msg += f'{k}: {v}\n'


        self.message_post(body=msg)


    def _cron_process_documents_status(self, job_count=20):
        """Send to SRI all documents marked as to send"""
        # Retrieve documents to send
        docs = self.search([('state', '=', 'to_send')])
        for doc in docs:
            doc.action_check_document_status()


    def action_ride_download(self):
        url = self.company_id.invoixo_url + "/v1.0/edoc/ride/factura/pdf/" + self.name
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new'
        }
