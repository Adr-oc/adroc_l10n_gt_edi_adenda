import logging
from lxml import etree

from odoo import models
from odoo.tools import cleanup_xml_node

DTE_NS = "{http://www.sat.gob.gt/dte/fel/0.2.0}"
DTE_NS_URL = "http://www.sat.gob.gt/dte/fel/0.2.0"


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

    def _l10n_gt_edi_modify_receptor(self, xml_string):
        """
        Modifica la sección Receptor del XML para agregar:
        - CorreoReceptor como atributo
        - DireccionReceptor con sus subelementos (Direccion, CodigoPostal, Municipio, Departamento, Pais)
        """
        self.ensure_one()
        partner = self.commercial_partner_id

        logging.info("=== RECEPTOR: Iniciando _l10n_gt_edi_modify_receptor ===")
        logging.info("RECEPTOR: Partner: %s", partner.name)

        # Parsear el XML
        root = etree.fromstring(xml_string.encode('utf-8'))
        nsmap = {'dte': DTE_NS_URL}

        # Buscar el elemento Receptor
        receptor = root.find('.//dte:Receptor', nsmap)
        if receptor is None:
            logging.warning("RECEPTOR: No se encontró elemento Receptor en el XML")
            return xml_string

        logging.info("RECEPTOR: Elemento Receptor encontrado")

        # Agregar CorreoReceptor si el partner tiene email
        if partner.email:
            receptor.set('CorreoReceptor', partner.email)
            logging.info("RECEPTOR: CorreoReceptor agregado: %s", partner.email)

        # Verificar si ya existe DireccionReceptor
        direccion_receptor = receptor.find('dte:DireccionReceptor', nsmap)

        if direccion_receptor is None:
            logging.info("RECEPTOR: Creando DireccionReceptor")
            # Crear DireccionReceptor
            direccion_receptor = etree.SubElement(receptor, DTE_NS + 'DireccionReceptor')

            # Construir dirección completa
            direccion_full = ''
            if partner.street:
                direccion_full = partner.street
            else:
                direccion_full = 'Ciudad'
            if partner.street2:
                direccion_full += ' ' + partner.street2

            # Agregar subelementos
            direccion_elem = etree.SubElement(direccion_receptor, DTE_NS + 'Direccion')
            direccion_elem.text = direccion_full

            codigo_postal_elem = etree.SubElement(direccion_receptor, DTE_NS + 'CodigoPostal')
            codigo_postal_elem.text = partner.zip or '01001'

            municipio_elem = etree.SubElement(direccion_receptor, DTE_NS + 'Municipio')
            municipio_elem.text = partner.city or 'Guatemala'

            departamento_elem = etree.SubElement(direccion_receptor, DTE_NS + 'Departamento')
            departamento_elem.text = partner.state_id.name if partner.state_id else 'Guatemala'

            pais_elem = etree.SubElement(direccion_receptor, DTE_NS + 'Pais')
            pais_elem.text = partner.country_id.code or 'GT'

            logging.info("RECEPTOR: DireccionReceptor creada - Direccion: %s, CP: %s, Municipio: %s, Depto: %s, Pais: %s",
                        direccion_full, partner.zip or '01001', partner.city or 'Guatemala',
                        partner.state_id.name if partner.state_id else 'Guatemala',
                        partner.country_id.code or 'GT')
        else:
            logging.info("RECEPTOR: DireccionReceptor ya existe - no se modifica")

        result_xml = etree.tostring(root, pretty_print=True, encoding='unicode')
        logging.info("=== RECEPTOR: XML modificado exitosamente ===")

        return result_xml

    def _l10n_gt_edi_modify_adenda(self, xml_string):
        """
        Modifica la sección Adenda del XML generado.
        Reemplaza el contenido de Adenda con Complemento03.
        Solo aplica para empresas con ID: 6, 15, 16, 18
        """
        self.ensure_one()

        logging.info("=== ADENDA: Iniciando _l10n_gt_edi_modify_adenda ===")
        logging.info("ADENDA: Factura %s, Company ID: %s, Company Name: %s",
                     self.name, self.company_id.id, self.company_id.name)

        # Solo aplicar para estas empresas
        EMPRESAS_ADENDA = [6, 15, 16, 18]
        if self.company_id.id not in EMPRESAS_ADENDA:
            logging.info("ADENDA: Company ID %s NO está en lista %s - SALTANDO",
                         self.company_id.id, EMPRESAS_ADENDA)
            return xml_string

        logging.info("ADENDA: Company ID %s SÍ está en lista - PROCESANDO", self.company_id.id)

        complemento03 = self._l10n_gt_edi_get_adenda_complemento03()
        logging.info("ADENDA: Complemento03 generado: '%s'", complemento03)

        # Parsear el XML
        root = etree.fromstring(xml_string.encode('utf-8'))
        nsmap = {'dte': 'http://www.sat.gob.gt/dte/fel/0.2.0'}

        # Buscar el elemento SAT
        sat_element = root.find('.//dte:SAT', nsmap)
        if sat_element is None:
            logging.warning("ADENDA: No se encontró elemento SAT en el XML")
            return xml_string

        logging.info("ADENDA: Elemento SAT encontrado")

        # Buscar Adenda existente
        adenda = sat_element.find('dte:Adenda', nsmap)

        if adenda is not None:
            logging.info("ADENDA: Adenda existente encontrada - limpiando contenido")
            # Limpiar contenido existente
            for child in list(adenda):
                adenda.remove(child)
        else:
            logging.info("ADENDA: No existe Adenda - creando nueva")
            # Crear nueva Adenda (con namespace dte:)
            adenda = etree.SubElement(sat_element, '{http://www.sat.gob.gt/dte/fel/0.2.0}Adenda')

        # Agregar Complemento03 SIN namespace (así lo espera el SAT)
        complemento_elem = etree.SubElement(adenda, 'Complemento03')
        complemento_elem.text = complemento03 or ''
        logging.info("ADENDA: Complemento03 agregado a Adenda")

        result_xml = etree.tostring(root, pretty_print=True, encoding='unicode')
        logging.info("=== ADENDA: XML modificado exitosamente ===")

        return result_xml

    def _l10n_gt_edi_try_send(self):
        """
        Sobrescribe el método de envío para modificar la Adenda antes de enviar.
        """
        from odoo.addons.l10n_gt_edi.models.utils import _l10n_gt_edi_send_to_sat
        from odoo import _

        logging.info("=== ADENDA: MÉTODO _l10n_gt_edi_try_send SOBRESCRITO EJECUTÁNDOSE ===")
        logging.info("ADENDA: Factura: %s, ID: %s", self.name, self.id)

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

        # MODIFICACIÓN: Agregar datos de Receptor (CorreoReceptor, DireccionReceptor)
        logging.info("RECEPTOR: Llamando a _l10n_gt_edi_modify_receptor")
        xml_data = self._l10n_gt_edi_modify_receptor(xml_data)

        # MODIFICACIÓN: Agregar Adenda personalizada
        logging.info("ADENDA: Llamando a _l10n_gt_edi_modify_adenda")
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

            # AUTO-LLENAR: Copiar series y serial_number a account.move
            self._l10n_gt_edi_update_invoice_fel_fields(result)

            self.message_post(body=_("Successfully sent the XML to the SAT"), attachment_ids=self.l10n_gt_edi_attachment_id.ids)
            if sudo_root_company.l10n_gt_edi_service_provider == 'demo':
                self.message_post(body=_("This document has been successfully generated in DEMO mode. "
                                         "It is considered as accepted and it won't be sent to the SAT."))
            self._cr.commit()

    def _l10n_gt_edi_update_invoice_fel_fields(self, result):
        """
        Actualiza los campos FEL de la factura con la respuesta de INFILE.
        - series → invoice_series, x_studio_serie
        - serial_number → invoice_number, x_studio_nmero_de_dte
        """
        self.ensure_one()

        series = result.get('series', '')
        serial_number = result.get('serial_number', '')

        vals = {}

        # Campos de mrdc_shipment_base
        if 'invoice_series' in self._fields:
            vals['invoice_series'] = series
        if 'invoice_number' in self._fields:
            vals['invoice_number'] = serial_number

        # Campos legacy de fel_gt/sam_gt
        if 'x_studio_serie' in self._fields:
            vals['x_studio_serie'] = series
        if 'x_studio_nmero_de_dte' in self._fields:
            vals['x_studio_nmero_de_dte'] = serial_number

        if vals:
            self.write(vals)
            logging.info("FEL: Campos actualizados - Serie: %s, Número: %s", series, serial_number)

    def action_sync_fel_fields_from_document(self):
        """
        Sincroniza invoice_series e invoice_number desde el documento FEL.
        Se puede llamar manualmente o desde un cron/action.
        Útil para actualización retroactiva de facturas existentes.
        """
        for move in self:
            fel_doc = move.l10n_gt_edi_document_ids.filtered(
                lambda d: d.state == 'invoice_sent'
            ).sorted('id', reverse=True)[:1]

            if fel_doc:
                vals = {}
                if 'invoice_series' in move._fields and fel_doc.series:
                    vals['invoice_series'] = fel_doc.series
                if 'invoice_number' in move._fields and fel_doc.serial_number:
                    vals['invoice_number'] = fel_doc.serial_number
                if 'x_studio_serie' in move._fields and fel_doc.series:
                    vals['x_studio_serie'] = fel_doc.series
                if 'x_studio_nmero_de_dte' in move._fields and fel_doc.serial_number:
                    vals['x_studio_nmero_de_dte'] = fel_doc.serial_number

                if vals:
                    move.write(vals)
                    logging.info("FEL Sync: Factura %s actualizada - Serie: %s, Número: %s",
                                 move.name, fel_doc.series, fel_doc.serial_number)
