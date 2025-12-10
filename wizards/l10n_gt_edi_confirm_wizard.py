from odoo import fields, models, api, _


class L10nGtEdiConfirmWizard(models.TransientModel):
    _name = 'l10n_gt_edi.confirm.wizard'
    _description = 'Wizard para confirmar certificación FEL al publicar factura'

    move_ids = fields.Many2many(
        'account.move',
        string="Facturas",
        required=True,
    )

    # Campos informativos
    invoice_count = fields.Integer(
        string="Número de Facturas",
        compute="_compute_invoice_info",
    )
    invoice_names = fields.Text(
        string="Facturas a certificar",
        compute="_compute_invoice_info",
    )
    total_amount = fields.Float(
        string="Monto Total",
        compute="_compute_invoice_info",
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Moneda",
        compute="_compute_invoice_info",
    )

    @api.depends('move_ids')
    def _compute_invoice_info(self):
        for wizard in self:
            wizard.invoice_count = len(wizard.move_ids)
            wizard.invoice_names = '\n'.join([
                f"• {m.name or 'Borrador'} - {m.partner_id.name} - {m.amount_total:,.2f} {m.currency_id.symbol}"
                for m in wizard.move_ids
            ])
            wizard.total_amount = sum(wizard.move_ids.mapped('amount_total'))
            wizard.currency_id = wizard.move_ids[:1].currency_id if wizard.move_ids else False

    def action_confirm_with_fel(self):
        """Confirma la(s) factura(s) y certifica en FEL"""
        self.ensure_one()
        return self.move_ids.action_post_with_fel()

    def action_confirm_without_fel(self):
        """Confirma la(s) factura(s) sin certificar en FEL (se certificará al enviar)"""
        self.ensure_one()
        return self.move_ids.action_post_without_fel()

    def action_cancel(self):
        """Cancela y no hace nada"""
        return {'type': 'ir.actions.act_window_close'}
