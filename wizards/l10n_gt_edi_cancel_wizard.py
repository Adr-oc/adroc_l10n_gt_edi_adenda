from odoo import fields, models, api, _
from odoo.exceptions import UserError


class L10nGtEdiCancelWizard(models.TransientModel):
    _name = 'l10n_gt_edi.cancel.wizard'
    _description = 'Wizard para anular factura FEL en INFILE'

    move_id = fields.Many2one('account.move', string="Factura", required=True)
    reason = fields.Text(
        string="Motivo de Anulación",
        required=True,
        help="Ingrese el motivo de anulación (máximo 255 caracteres)"
    )

    # Campos informativos (readonly)
    invoice_name = fields.Char(
        string="Número de Factura",
        related='move_id.name',
        readonly=True
    )
    partner_name = fields.Char(
        string="Cliente",
        related='move_id.partner_id.name',
        readonly=True
    )
    invoice_date = fields.Date(
        string="Fecha de Factura",
        related='move_id.invoice_date',
        readonly=True
    )
    amount_total = fields.Monetary(
        string="Monto Total",
        related='move_id.amount_total',
        readonly=True
    )
    currency_id = fields.Many2one(
        related='move_id.currency_id',
        readonly=True
    )
    fel_uuid = fields.Char(
        string="UUID FEL",
        compute='_compute_fel_uuid',
        readonly=True
    )
    fel_series = fields.Char(
        string="Serie FEL",
        compute='_compute_fel_uuid',
        readonly=True
    )
    fel_number = fields.Char(
        string="Número FEL",
        compute='_compute_fel_uuid',
        readonly=True
    )

    @api.depends('move_id')
    def _compute_fel_uuid(self):
        for wizard in self:
            fel_doc = wizard.move_id.l10n_gt_edi_document_ids.filtered(
                lambda d: d.state == 'invoice_sent'
            ).sorted('id', reverse=True)[:1]
            wizard.fel_uuid = fel_doc.uuid if fel_doc else ''
            wizard.fel_series = fel_doc.series if fel_doc else ''
            wizard.fel_number = fel_doc.serial_number if fel_doc else ''

    @api.constrains('reason')
    def _check_reason_length(self):
        for wizard in self:
            if wizard.reason and len(wizard.reason) > 255:
                raise UserError(_("El motivo de anulación no puede exceder 255 caracteres. "
                                "Actualmente tiene %d caracteres.") % len(wizard.reason))

    def action_cancel_fel(self):
        """Ejecuta la anulación en INFILE"""
        self.ensure_one()

        if not self.reason or not self.reason.strip():
            raise UserError(_("Debe ingresar un motivo de anulación"))

        if len(self.reason) > 255:
            raise UserError(_("El motivo no puede exceder 255 caracteres"))

        # Ejecutar anulación
        self.move_id._l10n_gt_edi_cancel_invoice(self.reason.strip())

        return {'type': 'ir.actions.act_window_close'}
