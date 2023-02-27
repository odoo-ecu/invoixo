# -*- coding: utf-8 -*-
from odoo import fields, models


class InvoixoMessageWizard(models.TransientModel):
    _name = "invoixo.message.wizard"
    _description = "Message wizard to display some messages"

    def get_default(self):
        if self.env.context.get("message", False):
            return self.env.context.get("message")
        return False

    name = fields.Text("Message", readonly=True, default=get_default)
