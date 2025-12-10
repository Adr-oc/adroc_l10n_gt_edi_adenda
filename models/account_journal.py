from odoo import fields, models, api


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_gt_edi_phrase_ids = fields.Many2many(
        comodel_name='l10n_gt_edi.phrase',
        relation='account_journal_l10n_gt_edi_phrase_rel',
        column1='journal_id',
        column2='phrase_id',
        string="Frases FEL",
        help="Frases FEL específicas para este diario. Si se asignan, estas frases "
             "tendrán prioridad sobre las frases de la compañía y del cliente.",
    )
    l10n_gt_edi_use_journal_phrases = fields.Boolean(
        string="Usar Frases del Diario",
        default=False,
        help="Si está activo, las facturas de este diario usarán las frases "
             "configuradas aquí en lugar de las de la compañía/cliente.",
    )
