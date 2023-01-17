# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResCompany(models.Model):
    """Res Company Inheritance"""
    _inherit = 'res.company'

    invoixo_url = fields.Char('URL')
    invoixo_signature = fields.Binary('Signature')
    invoixo_signature_password = fields.Char('Signature Password')
    invoixo_password = fields.Char('Electronic Invoicing Password')




