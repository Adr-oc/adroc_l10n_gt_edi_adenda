from lxml import etree

from odoo import models
from odoo.tools import cleanup_xml_node


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_gt_edi_get_adenda_complemento03(self):
        """
        Construye el texto del Complemento03 para la Adenda.

        Formato: BL {bl}  DUCA  {referencia_2} EMBARQUE {embarque} REFERENCIA {referencia_3}

        Campos utilizados:
        - bl: BL/Contenedor (de adroc_shipment_fixes)
        - referencia_2: DUCA/Declaración (de sam_gt)
        - referencia_3: Referencia (de sam_gt)
        - mrdc_shipment_id.name: Nombre del embarque (de mrdc_shipment_base)
        """
        self.ensure_one()
        partes = []

        # BL
        if self.bl:
            partes.append(f"BL {self.bl}")

        # DUCA (referencia_2)
        if self.referencia_2:
            partes.append(f"DUCA  {self.referencia_2}")

        # EMBARQUE
        embarque = self.mrdc_shipment_id.name if self.mrdc_shipment_id else ''
        if embarque:
            partes.append(f"EMBARQUE {embarque}")

        # REFERENCIA (referencia_3)
        if self.referencia_3:
            partes.append(f"REFERENCIA {self.referencia_3}")

        return ' '.join(partes)

    def _l10n_gt_edi_modify_adenda(self, xml_string):
        """
        Modifica la sección Adenda del XML generado.
        Reemplaza el contenido de Adenda con Complemento03.
        Solo aplica para empresas con ID: 6, 15, 16, 18
        """
        self.ensure_one()

        # Solo aplicar para estas empresas
        EMPRESAS_ADENDA = [6, 15, 16, 18]
        if self.company_id.id not in EMPRESAS_ADENDA:
            return xml_string

        complemento03 = self._l10n_gt_edi_get_adenda_complemento03()

        # Parsear el XML
        root = etree.fromstring(xml_string.encode('utf-8'))
        nsmap = {'dte': 'http://www.sat.gob.gt/dte/fel/0.2.0'}

        # Buscar el elemento SAT
        sat_element = root.find('.//dte:SAT', nsmap)
        if sat_element is None:
            return xml_string

        # Buscar Adenda existente
        adenda = sat_element.find('dte:Adenda', nsmap)

        if adenda is not None:
            # Limpiar contenido existente
            for child in list(adenda):
                adenda.remove(child)
        else:
            # Crear nueva Adenda (con namespace dte:)
            adenda = etree.SubElement(sat_element, '{http://www.sat.gob.gt/dte/fel/0.2.0}Adenda')

        # Agregar Complemento03 SIN namespace (así lo espera el SAT)
        complemento_elem = etree.SubElement(adenda, 'Complemento03')
        complemento_elem.text = complemento03 or ''

        return etree.tostring(root, pretty_print=True, encoding='unicode')

    def _l10n_gt_edi_send_to_sat(self):
        """
        Sobrescribe el método de envío para modificar la Adenda antes de enviar.
        """
        from odoo.addons.l10n_gt_edi.models.utils import _l10n_gt_edi_send_to_sat
        from odoo import _

        self.ensure_one()
        self.env['res.company']._with_locked_records(self)

        # Pre-send validation
        if errors := self._l10n_gt_edi_get_pre_send_errors():
            self._l10n_gt_edi_create_document_invoice_sending_failed({'errors': errors})
            return

        # Construct the XML
        gt_values = {}
        self._l10n_gt_edi_add_base_values(gt_values)
        if gt_values['have_exportacion']:
            self._l10n_gt_edi_add_export_values(gt_values)
        if gt_values['have_referencias']:
            self._l10n_gt_edi_add_reference_values(gt_values)
        if gt_values['have_cambiaria']:
            self._l10n_gt_edi_add_payment_values(gt_values)

        xml_data = self.env['ir.qweb']._render('l10n_gt_edi.SAT', gt_values)
        xml_data = etree.tostring(cleanup_xml_node(xml_data, remove_blank_nodes=False), pretty_print=True, encoding='unicode')

        # MODIFICACIÓN: Agregar Adenda personalizada
        xml_data = self._l10n_gt_edi_modify_adenda(xml_data)

        sudo_root_company = self.company_id.sudo().parent_ids.filtered('partner_id.vat')[-1:] or self.company_id.sudo().root_id

        # Send the XML to Infile
        db_uuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        result = _l10n_gt_edi_send_to_sat(
            company=sudo_root_company,
            xml_data=xml_data,
            identification_key=f"{db_uuid}_{self._l10n_gt_edi_get_name()}",
        )

        # Remove all previous error documents
        self.l10n_gt_edi_document_ids.filtered(lambda d: d.state == 'invoice_sending_failed').unlink()

        # Create Error/Successful Document
        if 'errors' in result:
            self._l10n_gt_edi_create_document_invoice_sending_failed({**result, 'xml': xml_data})
        else:
            self._l10n_gt_edi_create_document_invoice_sent(result)
            self.message_post(body=_("Successfully sent the XML to the SAT"), attachment_ids=self.l10n_gt_edi_attachment_id.ids)
            if sudo_root_company.l10n_gt_edi_service_provider == 'demo':
                self.message_post(body=_("This document has been successfully generated in DEMO mode. "
                                         "It is considered as accepted and it won't be sent to the SAT."))
