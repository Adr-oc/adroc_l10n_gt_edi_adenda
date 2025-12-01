{
    'name': 'Guatemala EDI - Adenda Personalizada',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations/EDI',
    'summary': 'Agrega campos de referencia a la Adenda del XML FEL Guatemala',
    'description': """
        Este módulo extiende la funcionalidad de facturación electrónica de Guatemala
        para incluir campos de referencia personalizados en la sección Adenda del XML.

        Campos incluidos:
        - Complemento01: bl (BL/Contenedor)
        - Complemento02: referencia_2 (Declaración)
        - Complemento03: referencia_3 (Observaciones)
        - Complemento04: mrdc_shipment_id.name o name (Embarque/Factura)
    """,
    'author': 'ADROC',
    'website': 'https://www.adroc.com.gt',
    'depends': [
        'l10n_gt_edi',
        'sam_gt',
        'adroc_shipment_fixes',
        'mrdc_shipment_base',
    ],
    'data': [
        'data/templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
