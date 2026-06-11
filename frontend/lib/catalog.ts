/**
 * Document Type Catalog — grouped dropdown (SPEC.md, exact Spanish labels
 * and group emojis). These labels are mandated verbatim by the spec and are
 * therefore NOT routed through the i18n dictionary: the catalog is Spanish
 * in every UI language at launch.
 */

export interface DocTypeOption {
  value: string;
  label: string;
}

export interface DocTypeGroup {
  emoji: string;
  label: string;
  options: DocTypeOption[];
}

export const DOC_TYPE_CATALOG: DocTypeGroup[] = [
  {
    emoji: "🏛",
    label: "Gobierno Corporativo",
    options: [
      { value: "acta_reunion_consejo", label: "Acta de Reunión del Consejo" },
      { value: "resolucion_consejo_per_rollam", label: "Resolución del Consejo per rollam" },
      { value: "acta_junta_general", label: "Acta de Junta General" },
      { value: "resolucion_junta_sin_reunion", label: "Resolución de Junta General sin Reunión" },
      { value: "nombramiento_cese_administrador", label: "Nombramiento / Cese de Administrador" },
      { value: "poder_general", label: "Poder General (Delegación de Facultades)" },
      { value: "poder_especial", label: "Poder Especial" },
    ],
  },
  {
    emoji: "💼",
    label: "Operaciones de Fondo",
    options: [
      { value: "llamada_capital", label: "Llamada de Capital (Capital Call Notice)" },
      { value: "distribucion_inversores", label: "Distribución a Inversores (Distribution Notice)" },
      { value: "extension_periodo_inversion", label: "Extensión del Período de Inversión" },
      { value: "extension_plazo_fondo", label: "Extensión del Plazo del Fondo" },
      { value: "certificado_participacion_inversor", label: "Certificado de Participación del Inversor" },
      { value: "waiver_renuncia", label: "Waiver / Renuncia a Derecho Contractual" },
    ],
  },
  {
    emoji: "📋",
    label: "Gestión de Portfolio",
    options: [
      { value: "term_sheet", label: "Term Sheet (no vinculante)" },
      { value: "carta_intenciones", label: "Carta de Intenciones (LOI)" },
      { value: "nda", label: "NDA / Acuerdo de Confidencialidad" },
      { value: "acuerdo_suscripcion", label: "Acuerdo de Suscripción de Participaciones" },
      { value: "resolucion_aprobacion_inversion", label: "Resolución de Aprobación de Inversión" },
      { value: "resolucion_follow_on", label: "Resolución de Seguimiento (Follow-on)" },
      { value: "resolucion_desinversion", label: "Resolución de Desinversión" },
    ],
  },
  {
    emoji: "⚖️",
    label: "Cumplimiento y Regulatorio",
    options: [
      { value: "certificado_ubo", label: "Certificado de Titularidad Real (UBO)" },
      { value: "declaracion_aml_kyc", label: "Declaración AML/KYC" },
      { value: "certificado_residencia_fiscal", label: "Certificado de Residencia Fiscal" },
      { value: "comunicacion_regulador", label: "Comunicación a Regulador (CNMV / AMF / BaFin)" },
      { value: "notificacion_aifmd", label: "Notificación AIFMD" },
    ],
  },
  {
    emoji: "📝",
    label: "Contratos con Terceros",
    options: [
      { value: "contrato_prestacion_servicios", label: "Contrato de Prestación de Servicios" },
      { value: "acuerdo_asesoramiento", label: "Acuerdo de Asesoramiento (Advisory Agreement)" },
      { value: "contrato_gestor_delegado", label: "Contrato de Gestor de Cartera Delegado" },
      { value: "side_letter_inversor", label: "Side Letter con Inversor" },
    ],
  },
  {
    emoji: "🔧",
    label: "Otros",
    options: [{ value: "other", label: "Other (describir abajo)" }],
  },
];

const LABEL_BY_VALUE: Record<string, string> = Object.fromEntries(
  DOC_TYPE_CATALOG.flatMap((g) => g.options.map((o) => [o.value, o.label])),
);

export function docTypeLabel(value: string): string {
  return LABEL_BY_VALUE[value] ?? value;
}

export function docTypeGroupLabel(group: DocTypeGroup): string {
  return `${group.emoji} ${group.label}`;
}
