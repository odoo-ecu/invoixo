{
    'name': 'Invoixo Base',
    'version': '16.0.1.0.0',
    'description': 'Invoixo Base',
    'summary': 'Base module for invoixo electronic invoicing service',
    'author': 'Marcelo Mora <marcelo.mora@accioma.com>',
    'website': 'https://accioma.com',
    'license': 'LGPL-3',
    'category': 'Accounting',
    'depends': [
        'l10n_ec_edi'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/res_company_views.xml',
        'views/l10n_ec_edi_document_views.xml',
        'wizard/message_wizard_view.xml',
    ],
    'auto_install': False,
    'application': False,
    'assets': {

    }
}
