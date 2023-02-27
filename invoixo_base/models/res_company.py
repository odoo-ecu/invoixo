# -*- coding: utf-8 -*-
import requests, json
import logging, base64
from io import StringIO
from odoo import models, fields, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    """Res Company Inheritance"""
    _inherit = 'res.company'

    invoixo_url = fields.Char('URL')
    invoixo_signature = fields.Binary('Signature')
    invoixo_signature_password = fields.Char('Signature Password')
    invoixo_password = fields.Char('Electronic Invoicing Password')

    # Status
    invoixo_token = fields.Char("Token")
    invoixo_is_registered = fields.Boolean("Is Registered")

    def action_invoixo_register(self):
        self.ensure_one()

        url = self.invoixo_url + "/v1.0/company/register"
        payload = json.dumps({
            "ruc": self.vat,
            "password": self.invoixo_password,
            "signature_password": self.invoixo_signature_password,
            "legal_name": self.name,
            "trade_name": self.partner_id.tradename
        })

        files = [
            ('logo', ("{}.logo", self.logo, 'application/octet')),
            ('signature', ("{}.pk12".format(self.vat), self.invoixo_signature, 'application/octet')),
            ('data', ("payload", payload, 'application/json')),
        ]

        response = requests.post(url, files=files)

        if response.status_code == 200:
            r = response.json()
            if r['error'] == 'error':
                raise ValidationError(r['msg'])

            _logger.info("Error {}".format(r["error"]))

            if r['error'] == 'success':
                view = self.env.ref("invoixo_base.view_invoixo_message_form")
                view_id = view and view.id or False
                context = dict(self._context or {})
                context["message"] = r['msg']
                return {
                    'name': _('Success'),
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'invoixo.message.wizard',
                    'views': [(view_id, 'form')],
                    'view_id': view_id,
                    'target': 'new',
                    'context': context,
                }











