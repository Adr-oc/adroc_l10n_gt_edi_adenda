import logging
import requests
from datetime import datetime, timezone
from json import JSONDecodeError
from zoneinfo import ZoneInfo

from lxml import etree

from odoo import models, fields, api, _
from odoo.tools import cleanup_xml_node
from odoo.exceptions import UserError

DTE_NS = "{http://www.sat.gob.gt/dte/fel/0.2.0}"
DTE_NS_URL = "http://www.sat.gob.gt/dte/fel/0.2.0"


class AccountMove(models.Model):
    _inherit = 'account.move'

    # =========================================================================
    # CAMPOS ADICIONALES PARA COMPLEMENTO DE EXPORTACIÓN
    # =========================================================================
    comprador_fel = fields.Many2one(
        'res.partner',
        string="Comprador FEL",
        help="Comprador para facturas de exportación. Si no se especifica, se usa el consignatario.",
    )
    exportador_fel = fields.Many2one(
        'res.partner',
        string="Exportador FEL",
        help="Exportador para facturas de exportación. Si no se especifica, se usa la compañía.",
    )
    otra_referencia_fel = fields.Char(
        string="Otra Referencia FEL",
        size=50,
        help="Otra referencia para el complemento de exportación.",
    )
    is_export_invoice = fields.Boolean(
        string="Es Factura de Exportación",
        compute="_compute_is_export_invoice",
        store=True,
        help="Indica si es una factura de exportación basado en la posición fiscal.",
    )

    @api.depends('fiscal_position_id', 'country_code')
    def _compute_is_export_invoice(self):
        """
        Determina si es factura de exportación basándose en la posición fiscal.
        Busca posiciones fiscales que NO tengan país asignado (exportación/cliente extranjero).
        """
        for move in self:
            # Es exportación si:
            # 1. País de la compañía es GT
            # 2. La posición fiscal NO tiene país asignado (Foreign/Extranjero)
            #    O el nombre contiene "Foreign" o "Extranjero"
            is_foreign_fp = False
            if move.fiscal_position_id:
                fp = move.fiscal_position_id
                # Posiciones fiscales de exportación típicamente no tienen país
                # o tienen nombre que indica cliente extranjero
                is_foreign_fp = (
                    not fp.country_id or
                    'foreign' in (fp.name or '').lower() or
                    'extranjero' in (fp.name or '').lower() or
                    'exporta' in (fp.name or '').lower()
                )
            move.is_export_invoice = move.country_code == 'GT' and is_foreign_fp

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

        # MODIFICACIÓN: Agregar campos adicionales al complemento de exportación
        logging.info("EXPORTACIÓN: Llamando a _l10n_gt_edi_modify_exportacion")
        xml_data = self._l10n_gt_edi_modify_exportacion(xml_data)

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

    # =========================================================================
    # ANULACIÓN FEL
    # =========================================================================

    def _l10n_gt_edi_can_cancel(self):
        """Verifica si la factura puede ser anulada en INFILE"""
        self.ensure_one()
        if self.l10n_gt_edi_state != 'invoice_sent':
            return False
        # Verificar que tiene documento FEL con UUID
        fel_doc = self.l10n_gt_edi_document_ids.filtered(
            lambda d: d.state == 'invoice_sent' and d.uuid
        )
        return bool(fel_doc)

    def action_open_cancel_fel_wizard(self):
        """Abre el wizard para anular factura FEL"""
        self.ensure_one()
        if not self._l10n_gt_edi_can_cancel():
            raise UserError(_("Esta factura no puede ser anulada en INFILE. "
                            "Debe estar en estado FEL 'Sent' con UUID válido."))

        return {
            'name': _('Anular Factura FEL'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_gt_edi.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    def _l10n_gt_edi_build_cancellation_xml(self, reason):
        """Construye el XML de anulación según XSD GT_AnulacionDocumento-0.1.0"""
        self.ensure_one()

        # Namespace para anulación (versión 0.1.0) - con prefijo dte:
        ANULACION_NS = "http://www.sat.gob.gt/dte/fel/0.1.0"

        # Obtener documento FEL original
        fel_doc = self.l10n_gt_edi_document_ids.filtered(
            lambda d: d.state == 'invoice_sent' and d.uuid
        ).sorted('id', reverse=True)[:1]

        if not fel_doc:
            raise UserError(_("No se encontró documento FEL válido para anular"))

        # Timezone Guatemala
        gt_tz = ZoneInfo('America/Guatemala')
        now = datetime.now(gt_tz)

        # Formatear fechas según XSD: aaaa-mm-ddThh:mm:ss.000-06:00
        fecha_emision = self.invoice_date.strftime('%Y-%m-%dT00:00:00.000-06:00')
        fecha_anulacion = now.strftime('%Y-%m-%dT%H:%M:%S.000-06:00')

        # NIT emisor (sin guión)
        nit_emisor = (self.company_id.partner_id.vat or '').replace('-', '').replace(' ', '')

        # NIT receptor
        nit_receptor = (self.partner_id.vat or '').replace('-', '').replace(' ', '')
        if not nit_receptor:
            nit_receptor = 'CF'

        # Construir XML con prefijo dte:
        nsmap = {'dte': ANULACION_NS}
        DTE = "{%s}" % ANULACION_NS

        root = etree.Element(DTE + 'GTAnulacionDocumento', nsmap=nsmap, Version="0.1")

        sat = etree.SubElement(root, DTE + 'SAT')
        anulacion_dte = etree.SubElement(sat, DTE + 'AnulacionDTE', ID="DatosCertificados")

        datos_generales = etree.SubElement(anulacion_dte, DTE + 'DatosGenerales')
        datos_generales.set('ID', 'DatosAnulacion')
        datos_generales.set('NumeroDocumentoAAnular', fel_doc.uuid)
        datos_generales.set('NITEmisor', nit_emisor)
        datos_generales.set('IDReceptor', nit_receptor)
        datos_generales.set('FechaEmisionDocumentoAnular', fecha_emision)
        datos_generales.set('FechaHoraAnulacion', fecha_anulacion)
        datos_generales.set('MotivoAnulacion', (reason or 'Anulación solicitada')[:255])

        xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(
            root,
            pretty_print=True,
            encoding='unicode'
        )

        logging.info("FEL Anulación: XML generado para factura %s, UUID: %s",
                     self.name, fel_doc.uuid)
        logging.info("FEL Anulación: XML completo:\n%s", xml_string)

        return xml_string

    def _l10n_gt_edi_send_cancellation(self, xml_data):
        """Envía XML de anulación a INFILE"""
        self.ensure_one()

        company = self.company_id.sudo()
        sudo_root_company = company.parent_ids.filtered('partner_id.vat')[-1:] or company.root_id

        # Demo mode
        if sudo_root_company.l10n_gt_edi_service_provider == 'demo':
            logging.info("FEL Anulación: Modo DEMO - simulando respuesta exitosa")
            return {
                'resultado': True,
                'uuid': 'DEMO-CANCEL-' + datetime.now().strftime('%Y%m%d%H%M%S'),
                'descripcion': 'Anulación exitosa en modo DEMO',
            }

        db_uuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')

        try:
            response = requests.post(
                url="https://certificador.feel.com.gt/fel/procesounificado/transaccion/v2/xml",
                headers={
                    'UsuarioFirma': sudo_root_company.l10n_gt_edi_ws_prefix,
                    'LlaveFirma': sudo_root_company.l10n_gt_edi_infile_token,
                    'UsuarioApi': sudo_root_company.l10n_gt_edi_ws_prefix,
                    'LlaveApi': sudo_root_company.l10n_gt_edi_infile_key,
                    'identificador': f"ODOO_CANCEL_{db_uuid}_{self.id}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}",
                },
                data=xml_data.encode('utf-8'),
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            logging.info("FEL Anulación: Respuesta de INFILE: %s", result)
            return result
        except JSONDecodeError as e:
            logging.error("FEL Anulación: Error decodificando respuesta JSON: %s", e)
            return {'errors': [f"Error en respuesta de INFILE: {str(e)}"]}
        except requests.RequestException as e:
            logging.error("FEL Anulación: Error de conexión: %s", e)
            return {'errors': [f"Error de conexión con INFILE: {str(e)}"]}
        except Exception as e:
            logging.error("FEL Anulación: Error inesperado: %s", e)
            return {'errors': [str(e)]}

    def _l10n_gt_edi_cancel_invoice(self, reason):
        """Proceso completo de anulación FEL"""
        self.ensure_one()

        logging.info("FEL Anulación: Iniciando anulación de factura %s", self.name)

        # Construir XML
        xml_data = self._l10n_gt_edi_build_cancellation_xml(reason)

        # Enviar a INFILE
        result = self._l10n_gt_edi_send_cancellation(xml_data)

        # Obtener documento original
        fel_doc = self.l10n_gt_edi_document_ids.filtered(
            lambda d: d.state == 'invoice_sent'
        ).sorted('id', reverse=True)[:1]

        # Verificar resultado
        has_errors = 'errors' in result
        is_success = result.get('resultado', False)

        if has_errors or not is_success:
            # Error en anulación
            if has_errors:
                error_msgs = result.get('errors', [])
            else:
                error_msgs = result.get('descripcion_errores', [])
                if isinstance(error_msgs, list) and error_msgs:
                    error_msgs = [e.get('mensaje_error', str(e)) for e in error_msgs]
                else:
                    error_msgs = [result.get('descripcion', 'Error desconocido de INFILE')]

            error_msg = ', '.join(error_msgs) if isinstance(error_msgs, list) else str(error_msgs)

            # Crear documento de error
            self.env['l10n_gt_edi.document'].create({
                'invoice_id': self.id,
                'state': 'invoice_cancelling_failed',
                'message': error_msg,
            })

            self.message_post(body=_("Error al anular en INFILE: %s") % error_msg)
            logging.error("FEL Anulación: Error - %s", error_msg)
            raise UserError(_("Error al anular en INFILE: %s") % error_msg)
        else:
            # Anulación exitosa
            cancellation_uuid = result.get('uuid', '')

            fel_doc.write({
                'state': 'invoice_cancelled',
                'cancellation_uuid': cancellation_uuid,
                'cancellation_date': fields.Datetime.now(),
                'cancellation_reason': reason,
            })

            # Cancelar la factura en Odoo
            self.button_cancel()

            self.message_post(
                body=_("Factura anulada exitosamente en INFILE. UUID Anulación: %s") % cancellation_uuid
            )
            logging.info("FEL Anulación: Éxito - Factura %s anulada, UUID: %s",
                        self.name, cancellation_uuid)

    # =========================================================================
    # COMPLEMENTO DE EXPORTACIÓN - CAMPOS ADICIONALES
    # =========================================================================

    def _l10n_gt_edi_modify_exportacion(self, xml_string):
        """
        Modifica el complemento de Exportación para agregar campos adicionales:
        - NombreComprador
        - DireccionComprador
        - CodigoComprador
        - NombreExportador
        - CodigoExportador

        Estos campos no están en el módulo original de Odoo l10n_gt_edi.
        """
        self.ensure_one()

        # Solo aplica para facturas de exportación (basado en posición fiscal)
        if not self.is_export_invoice:
            return xml_string

        logging.info("=== EXPORTACIÓN: Modificando complemento de exportación ===")

        CEX_NS = "http://www.sat.gob.gt/face2/ComplementoExportaciones/0.1.0"
        CEX = "{%s}" % CEX_NS

        # Parsear el XML
        root = etree.fromstring(xml_string.encode('utf-8'))

        # Buscar el elemento Exportacion
        exportacion = root.find('.//{%s}Exportacion' % CEX_NS)
        if exportacion is None:
            logging.warning("EXPORTACIÓN: No se encontró elemento Exportacion en el XML")
            return xml_string

        logging.info("EXPORTACIÓN: Elemento Exportacion encontrado")

        # Obtener datos del comprador (es el partner_id - a quien se emite la factura)
        comprador = self.commercial_partner_id
        if comprador:
            # Construir dirección del comprador
            direccion_comprador = self._l10n_gt_edi_build_partner_address(comprador)

            # Buscar si ya existe NombreComprador (para no duplicar)
            nombre_comprador_elem = exportacion.find(CEX + 'NombreComprador')
            if nombre_comprador_elem is None:
                # Insertar después de CodigoConsignatarioODestinatario
                codigo_consig = exportacion.find(CEX + 'CodigoConsignatarioODestinatario')
                if codigo_consig is not None:
                    idx = list(exportacion).index(codigo_consig) + 1
                else:
                    idx = len(exportacion)

                # NombreComprador
                nombre_comprador_elem = etree.Element(CEX + 'NombreComprador')
                nombre_comprador_elem.text = (comprador.name or '-')[:70]
                exportacion.insert(idx, nombre_comprador_elem)
                logging.info("EXPORTACIÓN: NombreComprador agregado: %s", comprador.name)

                # DireccionComprador
                direccion_comprador_elem = etree.Element(CEX + 'DireccionComprador')
                direccion_comprador_elem.text = direccion_comprador[:70]
                exportacion.insert(idx + 1, direccion_comprador_elem)
                logging.info("EXPORTACIÓN: DireccionComprador agregado: %s", direccion_comprador)

                # CodigoComprador - usa el NIT/DPI del comprador
                otra_ref = exportacion.find(CEX + 'OtraReferencia')
                if otra_ref is not None:
                    idx_codigo = list(exportacion).index(otra_ref)
                    codigo_comprador_elem = etree.Element(CEX + 'CodigoComprador')
                    # Usar VAT (NIT/DPI) del comprador, limpiar guiones
                    codigo_comprador = (comprador.vat or '').replace('-', '').strip() or '.'
                    codigo_comprador_elem.text = codigo_comprador
                    exportacion.insert(idx_codigo, codigo_comprador_elem)
                    logging.info("EXPORTACIÓN: CodigoComprador agregado: %s", codigo_comprador_elem.text)

        # Obtener datos del exportador (es la compañía que emite la factura)
        exportador = self.company_id.partner_id
        if exportador:
            # Buscar si ya existe NombreExportador
            nombre_exportador_elem = exportacion.find(CEX + 'NombreExportador')
            if nombre_exportador_elem is None:
                # Insertar al final
                nombre_exportador_elem = etree.SubElement(exportacion, CEX + 'NombreExportador')
                nombre_exportador_elem.text = (self.company_id.name or exportador.name)[:70]
                logging.info("EXPORTACIÓN: NombreExportador agregado: %s", nombre_exportador_elem.text)

                # CodigoExportador - usa el NIT de la compañía
                codigo_exportador_elem = etree.SubElement(exportacion, CEX + 'CodigoExportador')
                codigo_exportador = (exportador.vat or '').replace('-', '').strip() or '-'
                codigo_exportador_elem.text = codigo_exportador
                logging.info("EXPORTACIÓN: CodigoExportador agregado: %s", codigo_exportador_elem.text)

        # Actualizar OtraReferencia si se especificó otra_referencia_fel
        if self.otra_referencia_fel:
            otra_ref = exportacion.find(CEX + 'OtraReferencia')
            if otra_ref is not None:
                otra_ref.text = self.otra_referencia_fel
                logging.info("EXPORTACIÓN: OtraReferencia actualizado: %s", self.otra_referencia_fel)

        result_xml = etree.tostring(root, pretty_print=True, encoding='unicode')
        logging.info("=== EXPORTACIÓN: XML modificado exitosamente ===")

        return result_xml

    def _l10n_gt_edi_build_partner_address(self, partner):
        """Construye la dirección completa de un partner para el complemento de exportación."""
        partes = []
        if partner.street:
            partes.append(partner.street)
        else:
            partes.append('Ciudad')
        if partner.street2:
            partes.append(partner.street2)
        if partner.city:
            partes.append(partner.city)
        if partner.state_id:
            partes.append(partner.state_id.name)
        if partner.zip:
            partes.append(partner.zip)
        if partner.country_id:
            partes.append(partner.country_id.name)

        return ' '.join(partes)
