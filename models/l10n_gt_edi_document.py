from odoo import fields, models


class L10nGtEdiDocument(models.Model):
    _inherit = 'l10n_gt_edi.document'

    state = fields.Selection(
        selection_add=[
            ('invoice_cancelled', 'Cancelled'),
            ('invoice_cancelling_failed', 'Cancellation Failed'),
        ],
        ondelete={
            'invoice_cancelled': 'cascade',
            'invoice_cancelling_failed': 'cascade',
        }
    )
    cancellation_uuid = fields.Char(string="Cancellation UUID")
    cancellation_date = fields.Datetime(string="Cancellation Date")
    cancellation_reason = fields.Char(string="Cancellation Reason")
