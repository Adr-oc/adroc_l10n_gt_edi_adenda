# -*- encoding: utf-8 -*-
"""
Sobrescribe el wizard incompleto de fel_infile para agregar el método faltante.
Este wizard aparece al confirmar facturas - ejecuta directamente sin abrir más wizards.
"""

from odoo import models, api, _


class CertificarWizardFix(models.TransientModel):
    _inherit = 'fel.infile.certificar.wizard'

    def action_confirmar_certificacion(self):
        """
        Ejecuta la confirmación de la factura directamente.
        Si el journal tiene auto-certificación FEL, también certifica.
        NO abre más wizards - ejecuta directamente.
        """
        self.ensure_one()
        if not self.factura_id:
            return {'type': 'ir.actions.act_window_close'}

        move = self.factura_id

        # Confirmar la factura usando with_context para evitar nuestro wizard
        move = move.with_context(skip_fel_wizard=True)
        move.action_post()

        # Refrescar el move después del post
        move = self.factura_id

        # Si el journal tiene auto-certificación Y la factura aplica para FEL
        if (move.journal_id and
            move.journal_id.l10n_gt_edi_auto_certify and
            move.state == 'posted' and
            not move.l10n_gt_edi_state and
            move.country_code == 'GT' and
            move.l10n_gt_edi_doc_type):
            # Certificar en FEL
            move._l10n_gt_edi_try_send()

        return {'type': 'ir.actions.act_window_close'}
