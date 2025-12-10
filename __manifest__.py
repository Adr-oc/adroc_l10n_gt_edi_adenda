{
    'name': 'Guatemala EDI - Adenda Personalizada',
    'version': '19.0.4.0.0',
    'category': 'Accounting/Localizations/EDI',
    'summary': 'Adenda personalizada, certificación al confirmar, frases por journal y anulación FEL',
    'description': """
        Este módulo extiende la funcionalidad de facturación electrónica de Guatemala:

        Funcionalidades:
        - Frases FEL por Journal (prioridad sobre compañía/cliente)
        - Certificación FEL al confirmar factura (en lugar de al enviar)
        - Wizard de advertencia antes de certificar en FEL
        - Botón "Ver en Infile" siempre visible (incluso en facturas anuladas)
        - Adenda personalizada con Complemento03 (BL, DUCA, Embarque, Referencia)
        - Datos de Receptor (CorreoReceptor, DireccionReceptor)
        - Auto-llenado de invoice_series e invoice_number desde respuesta INFILE
        - Anulación de facturas FEL directamente en INFILE
    """,
    'author': 'ADROC',
    'website': 'https://www.adroc.com.gt',
    'depends': [
        'l10n_gt_edi',
        'sam_gt',
        'adroc_shipment_fixes',
        'mrdc_shipment_base',
        'fel_infile',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/templates.xml',
        'data/server_actions.xml',
        'wizards/l10n_gt_edi_cancel_wizard_views.xml',
        'wizards/l10n_gt_edi_confirm_wizard_views.xml',
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
