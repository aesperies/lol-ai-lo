/**
 * Minimal dictionary-based i18n.
 * - "es" is the default and reference dictionary (complete).
 * - "en" is complete.
 * - "fr" / "de" are shells: a few keys translated, everything else falls back to "es".
 *
 * NOTE — verbatim legal texts (Exit A acknowledgment, SLP disclaimer, Level-3
 * warning, unclassifiable-request message) are mandated VERBATIM in Spanish by
 * SPEC.md and are intentionally identical in every locale.
 */

export type Locale = "es" | "en" | "fr" | "de";

export const LOCALES: Locale[] = ["es", "en", "fr", "de"];
export const DEFAULT_LOCALE: Locale = "es";

export const LOCALE_LABELS: Record<Locale, string> = {
  es: "Español",
  en: "English",
  fr: "Français",
  de: "Deutsch",
};

/* ------------------------------------------------------------------ */
/* Verbatim texts from SPEC.md — DO NOT EDIT                           */
/* ------------------------------------------------------------------ */

const VERBATIM_EXIT_A_ACK =
  "Entiendo que este documento no ha sido revisado por un abogado y asumo la responsabilidad de su uso.";

const VERBATIM_SLP_DISCLAIMER =
  "Este documento ha sido generado por Lol-AI-lo Legal SLP. Su uso sin validación por abogado es responsabilidad exclusiva del cliente. Lol-AI-lo Legal SLP no asume responsabilidad por documentos descargados sin validación (Exit A).";

const VERBATIM_LEVEL3_WARNING =
  "Este documento se ha generado sin precedente de referencia. La validación por abogado es obligatoria antes de su uso.";

const VERBATIM_UNCLASSIFIABLE =
  "No hemos podido clasificar tu solicitud. Por favor reformúlala indicando el tipo de documento y las partes implicadas.";

/* ------------------------------------------------------------------ */
/* Reference dictionary (es)                                           */
/* ------------------------------------------------------------------ */

const es = {
  // App
  "app.name": "Lol-AI-lo",
  "app.tagline": "Documentación de fondos, generada y validada",

  // Common
  "common.loading": "Cargando…",
  "common.error": "Se ha producido un error. Inténtalo de nuevo.",
  "common.cancel": "Cancelar",
  "common.confirm": "Confirmar",
  "common.save": "Guardar",
  "common.edit": "Editar",
  "common.back": "Volver",
  "common.actions": "Acciones",
  "common.download": "Descargar",
  "common.upload": "Subir",
  "common.search": "Buscar",
  "common.all": "Todos",
  "common.empty": "No hay resultados.",
  "common.status": "Estado",
  "common.date": "Fecha",
  "common.fund": "Fondo",
  "common.docType": "Tipo de documento",
  "common.language": "Idioma",
  "common.email": "Email",
  "common.password": "Contraseña",
  "common.name": "Nombre",
  "common.role": "Rol",
  "common.logout": "Cerrar sesión",
  "common.optional": "opcional",
  "common.notAvailable": "No disponible",

  // Roles
  "role.client": "Cliente (fondo)",
  "role.counsel": "Abogado (counsel)",
  "role.admin": "Administrador",

  // Dev stub mode
  "dev.banner":
    "Modo desarrollo: Supabase no está configurado. Sesión simulada activa.",
  "dev.bannerRole": "Rol simulado:",
  "dev.chooseRole": "Selecciona un rol para entrar (modo desarrollo)",
  "dev.enterAs": "Entrar como {role}",

  // Navigation
  "nav.dashboard": "Panel",
  "nav.newRequest": "Nueva solicitud",
  "nav.documents": "Documentos",
  "nav.counselQueue": "Revisiones",
  "nav.gestoras": "Gestoras",
  "nav.precedents": "Precedentes",
  "nav.users": "Usuarios",
  "nav.quality": "Calidad y SLA",

  // Auth
  "auth.loginTitle": "Iniciar sesión",
  "auth.loginSubtitle": "Accede a tu espacio de documentación de fondos.",
  "auth.signIn": "Entrar",
  "auth.signupTitle": "Crear cuenta",
  "auth.signupSubtitle":
    "El rol y la gestora de tu cuenta los asigna el administrador del servicio.",
  "auth.signUp": "Registrarme",
  "auth.noAccount": "¿No tienes cuenta?",
  "auth.hasAccount": "¿Ya tienes cuenta?",
  "auth.goSignup": "Regístrate",
  "auth.goLogin": "Inicia sesión",
  "auth.signupDisabledStub":
    "El registro no está disponible en modo desarrollo. Usa la pantalla de inicio de sesión para elegir un rol simulado.",
  "auth.signupSuccess":
    "Cuenta creada. Revisa tu correo para confirmar la dirección.",
  "auth.invalidCredentials": "Credenciales no válidas.",

  // Statuses (7)
  "status.parsing": "Analizando",
  "status.confirmed": "Confirmada",
  "status.generating": "Generando",
  "status.review_pending": "Pendiente de revisión",
  "status.counsel_review": "En revisión por abogado",
  "status.validated": "Validada",
  "status.delivered": "Entregada",

  // Client dashboard
  "dashboard.title": "Mis solicitudes",
  "dashboard.subtitle": "Estado de tus solicitudes de documentos.",
  "dashboard.empty": "Todavía no has creado ninguna solicitud.",
  "dashboard.cta": "Nueva solicitud",
  "dashboard.viewDocument": "Ver documento",

  // Intake form
  "intake.title": "Nueva solicitud de documento",
  "intake.subtitle":
    "Describe el documento que necesitas. Nuestro motor lo generará a partir de los precedentes de tu gestora.",
  "intake.fund": "Fondo",
  "intake.fundPlaceholder": "Selecciona un fondo",
  "intake.docType": "Tipo de documento",
  "intake.docTypePlaceholder": "Selecciona un tipo de documento",
  "intake.docTypeCustom": "Describe el tipo de documento",
  "intake.docTypeCustomPlaceholder": "P. ej., acuerdo de co-inversión",
  "intake.freetext": "Descripción de la solicitud",
  "intake.freetextPlaceholder":
    "Describe el documento: partes implicadas, fechas, importes, condiciones especiales…",
  "intake.freetextPlaceholderStructured":
    "Contexto adicional, condiciones especiales…",
  "intake.structuredHeading": "Datos clave del documento",
  "intake.structuredHint":
    "Estos datos se incorporan al documento como valores confirmados y elevan la precisión del análisis.",
  "intake.partyPlaceholder": "Nombre de la persona o entidad",
  "intake.selectPlaceholder": "Selecciona una opción",
  "intake.charCount": "{count} / {max} caracteres",
  "intake.minChars": "Mínimo {min} caracteres.",
  "intake.counselToggle": "Validación por abogado",
  "intake.counselHint":
    "Un abogado de Lol-AI-lo Legal SLP revisará y validará el documento antes de su entrega.",
  "intake.assignedCounsel": "Abogado asignado",
  "intake.turnaround": "Plazo estimado de revisión: {hours} h laborables",
  "intake.noAssignedCounsel":
    "Un abogado del equipo de Lol-AI-lo Legal SLP será asignado a tu solicitud.",
  "intake.submit": "Generar Documento →",

  // Flow
  "flow.parsing": "Analizando tu solicitud…",
  "flow.parsingHint": "Extrayendo partes, fechas y términos clave.",
  "flow.generating": "Generando documento…",
  "flow.generatingHint":
    "Recuperando precedentes y redactando el borrador. Puede tardar hasta 60 segundos.",
  "flow.generationFailed": "La generación del documento ha fallado.",
  "flow.generationFailedHint":
    "Puedes reintentar la generación. Si el problema persiste, contacta con soporte.",
  "flow.retry": "Reintentar",

  // Parsed params review
  "params.title": "Revisión de parámetros",
  "params.subtitle":
    "Hemos extraído estos parámetros de tu solicitud. Revísalos y corrige lo necesario antes de generar.",
  "params.summary": "Resumen",
  "params.docTypeConfirmed": "Tipo de documento detectado",
  "params.languageDetected": "Idioma detectado",
  "params.parties": "Partes",
  "params.partyRole": "Rol",
  "params.partyName": "Nombre",
  "params.keyDates": "Fechas clave",
  "params.jurisdiction": "Jurisdicción",
  "params.governingLaw": "Ley aplicable",
  "params.keyTerms": "Términos clave",
  "params.confidence": "Confianza del análisis",
  "params.unclearBadge": "[UNCLEAR]",
  "params.unclearHint":
    "Los campos marcados como [UNCLEAR] tienen una confianza baja. Edítalos para poder continuar.",
  "params.notReady":
    "La solicitud no está lista para generar. Revisa los campos marcados.",
  "params.unclassifiable": VERBATIM_UNCLASSIFIABLE,
  "params.confirm": "Confirmar y Generar",
  "params.editedNote":
    "Las ediciones de parámetros quedan registradas en el historial de auditoría.",
  "params.backToIntake": "Reformular solicitud",
  "params.confirmedChip": "confirmado",

  // Structured intake field labels (backend models/doc_fields.py registry;
  // referenced via each spec's label_i18n_key)
  "docfields.importe_total": "Importe total",
  "docfields.fecha_limite_pago": "Fecha límite de pago",
  "docfields.porcentaje_compromiso": "Porcentaje sobre compromiso",
  "docfields.numero_llamada": "Nº de llamada",
  "docfields.importe": "Importe",
  "docfields.fecha": "Fecha",
  "docfields.concepto": "Concepto / origen",
  "docfields.contraparte": "Contraparte",
  "docfields.duracion_meses": "Duración (meses)",
  "docfields.modalidad": "Unilateral o recíproco",
  "docfields.fecha_reunion": "Fecha de la reunión",
  "docfields.asistentes": "Asistentes",
  "docfields.acuerdos_principales": "Acuerdos principales",
  "docfields.persona": "Persona",
  "docfields.cargo": "Cargo",
  "docfields.tipo": "Tipo",
  "docfields.fecha_efecto": "Fecha de efecto",
  "docfields.apoderado": "Apoderado",
  "docfields.facultades": "Facultades",
  "docfields.vigencia": "Vigencia",
  "docfields.compania_objetivo": "Compañía objetivo",
  "docfields.importe_inversion": "Importe de inversión",
  "docfields.valoracion_premoney": "Valoración pre-money",
  "docfields.tipo_instrumento": "Tipo de instrumento",
  "docfields.inversor": "Inversor",
  "docfields.derechos_solicitados": "Derechos solicitados",
  "docfields.fecha_referencia": "Fecha de referencia",
  "docfields.nueva_fecha": "Nueva fecha",
  "docfields.justificacion": "Justificación",

  // Document viewer / Exit A-B
  "viewer.title": "Documento generado",
  "viewer.downloadDraft": "Descargar Borrador",
  "viewer.downloadRedline": "Descargar Redline vs. Precedente",
  "viewer.exitATitle": "Me vale",
  "viewer.exitADesc":
    "Descarga el documento ahora, sin revisión por abogado, bajo tu responsabilidad.",
  "viewer.exitAAck": VERBATIM_EXIT_A_ACK,
  "viewer.exitAConfirm": "Confirmar y Descargar",
  "viewer.exitBTitle": "Validación por abogado",
  "viewer.exitBDesc":
    "Un abogado de Lol-AI-lo Legal SLP revisará el documento y te lo entregará validado.",
  "viewer.exitBRequest": "Solicitar Validación",
  "viewer.exitBRequested":
    "Validación solicitada. Recibirás un correo cuando el documento esté validado.",
  "viewer.level3Warning": VERBATIM_LEVEL3_WARNING,
  "viewer.missingBlocksExitA":
    "El documento contiene campos [MISSING] sin completar. La descarga directa (Exit A) está bloqueada: se requiere validación por abogado.",
  "viewer.disclaimer": VERBATIM_SLP_DISCLAIMER,
  "viewer.deliveredNote":
    "Documento entregado. Será candidato a precedente, pendiente de aprobación del administrador.",
  "viewer.validatedNote":
    "Documento validado por abogado y entregado. Se ha incorporado automáticamente a la biblioteca de precedentes.",
  "viewer.counselReviewNote":
    "El documento está en revisión por un abogado. Te avisaremos por correo cuando esté validado.",
  "viewer.notReadyYet": "El documento aún no está disponible.",
  "viewer.fallbackLevel": "Nivel de precedente",
  "viewer.requestMeta": "Detalle de la solicitud",
  "viewer.tabDraft": "Borrador",
  "viewer.tabRedline": "Redline vs. Precedente",
  "viewer.versionLabel": "Versión",
  "viewer.oldVersionBanner":
    "Estás viendo una versión anterior del documento. Vuelve a la última versión para descargar, solicitar ajustes o continuar con la entrega.",

  // Iterative refinements (Solicitar ajuste)
  "refine.title": "Solicitar ajuste",
  "refine.desc":
    "Describe en lenguaje natural el cambio que necesitas (p. ej., «cambia el plazo de preaviso a 15 días»). Regeneraremos el documento aplicándolo y conservando el historial de versiones.",
  "refine.placeholder":
    "P. ej., cambia el plazo de preaviso a 15 días naturales…",
  "refine.remaining": "Te quedan {count} ajustes",
  "refine.submit": "Solicitar ajuste",
  "refine.processing": "Aplicando ajuste…",
  "refine.processingHint":
    "Regenerando el documento con tu ajuste. Puede tardar hasta 60 segundos.",
  "refine.applied": "Ajuste aplicado. Mostrando la nueva versión.",
  "refine.failed": "No hemos podido aplicar el ajuste.",
  "refine.limitReached":
    "Has agotado los ajustes disponibles. Para más cambios, usa «Solicitar Validación» (validación por abogado).",

  // In-browser document viewer (HTML)
  "htmlViewer.loading": "Cargando documento…",
  "htmlViewer.error":
    "No se ha podido cargar el documento. Inténtalo de nuevo.",
  "htmlViewer.legend": "{ins} inserciones · {del} eliminaciones",

  // Documents history
  "documents.title": "Historial de documentos",
  "documents.subtitle": "Todas tus solicitudes y documentos generados.",
  "documents.filterStatus": "Estado",
  "documents.filterDocType": "Tipo de documento",
  "documents.filterFund": "Fondo",
  "documents.empty": "No hay documentos que coincidan con los filtros.",
  "documents.open": "Abrir",

  // Counsel
  "counsel.queueTitle": "Cola de revisión",
  "counsel.queueSubtitle":
    "Documentos pendientes de validación por abogado (Exit B).",
  "counsel.queueEmpty": "No hay revisiones pendientes.",
  "counsel.requestedBy": "Solicitado por",
  "counsel.review": "Revisar",
  // SLA chip (verde <50% · ámbar 50–100% · rojo >100% del SLA)
  "counsel.slaChip": "{hours} h / {sla} h SLA",
  "counsel.slaExceeded": "SLA superado · {hours} h",
  "counsel.reviewTitle": "Revisión de documento",
  "counsel.draftPane": "Borrador",
  "counsel.redlinePane": "Redline vs. Precedente",
  "counsel.editorTitle": "Editor del abogado",
  "counsel.editorHint":
    "Edita el texto directamente. Los cambios se guardan como versión de abogado (counsel_edit).",
  "counsel.editorPlaceholder": "El texto del borrador aparecerá aquí…",
  "counsel.saveEdit": "Guardar edición",
  "counsel.editSaved": "Edición guardada.",
  "counsel.comments": "Comentarios",
  "counsel.noComments": "Sin comentarios.",
  "counsel.addComment": "Añadir comentario",
  "counsel.commentPlaceholder": "Escribe un comentario o señala un problema…",
  "counsel.downloadDocx": "Descargar .docx",
  "counsel.uploadDocx": "Subir .docx editado",
  "counsel.uploadDone": "Archivo subido como versión de abogado.",
  "counsel.validate": "Validar y Entregar",
  "counsel.validatedOk":
    "Documento validado y entregado al cliente. Se ha incorporado a la biblioteca de precedentes.",

  // Admin — gestoras
  "admin.gestoras.title": "Gestoras",
  "admin.gestoras.subtitle":
    "Sociedades gestoras dadas de alta en la plataforma. Los datos están aislados por gestora.",
  "admin.gestoras.new": "Nueva gestora",
  "admin.gestoras.name": "Nombre",
  "admin.gestoras.tier": "Plan",
  "admin.gestoras.billingEmail": "Email de facturación",
  "admin.gestoras.funds": "Fondos",
  "admin.gestoras.create": "Crear gestora",
  "admin.gestoras.created": "Gestora creada.",

  // Admin — counsel assignments
  "admin.counsel.title": "Counsel asignado",
  "admin.counsel.subtitle":
    "Asigna abogados a cada gestora. Las notificaciones de validación (Exit B) se envían al abogado principal; sin asignación, a todos los abogados.",
  "admin.counsel.assign": "Asignar counsel",
  "admin.counsel.selectCounsel": "Selecciona un abogado",
  "admin.counsel.primary": "Principal",
  "admin.counsel.backup": "Suplente",
  "admin.counsel.makePrimary": "Hacer principal",
  "admin.counsel.remove": "Quitar",
  "admin.counsel.empty":
    "Sin counsel asignado: las notificaciones se envían a todos los abogados.",
  "admin.counsel.assigned": "Counsel asignado.",
  "admin.counsel.removed": "Asignación eliminada.",

  "tier.starter": "Starter",
  "tier.growth": "Growth",
  "tier.custom": "Custom",

  // Admin — precedents
  "admin.precedents.title": "Biblioteca de precedentes",
  "admin.precedents.subtitle":
    "Precedentes por gestora con control de versiones. Solo las versiones activas son base de generación.",
  "admin.precedents.upload": "Subir precedente",
  "admin.precedents.uploadHint":
    "Solo .docx puede ser base de generación; los PDF se indexan únicamente como referencia RAG.",
  "admin.precedents.uploaded": "Precedente subido (versión en borrador).",
  "admin.precedents.version": "Versión",
  "admin.precedents.ragWeight": "Peso RAG",
  "admin.precedents.activate": "Activar",
  "admin.precedents.supersede": "Sustituir",
  "admin.precedents.source": "Origen",
  "precedentStatus.draft": "Borrador",
  "precedentStatus.active": "Activa",
  "precedentStatus.superseded": "Sustituida",
  "precedentSource.manual_upload": "Subida manual",
  "precedentSource.validated_output": "Output validado",
  "precedentSource.slp_curated": "Curado SLP",
  "precedentSource.platform_base": "Base de plataforma",

  // Admin — users
  "admin.users.title": "Usuarios",
  "admin.users.subtitle": "Usuarios de la plataforma y sus roles.",
  "admin.users.invite": "Invitar usuario",
  "admin.users.gestora": "Gestora",
  "admin.users.invited": "Invitación enviada.",

  // Admin — quality & SLA (improvements #6 & #8)
  "admin.quality.title": "Calidad y SLA",
  "admin.quality.subtitle":
    "Calidad de la generación (cuánto cambia el abogado el borrador de la IA) y cumplimiento del SLA de revisión por abogado.",
  "admin.quality.qualityTitle": "Calidad por tipo de documento",
  "admin.quality.qualityHint":
    "Similitud 1,00 = documento entregado sin cambios respecto al borrador de la IA.",
  "admin.quality.count": "Docs",
  "admin.quality.avgSimilarity": "Similitud media",
  "admin.quality.pctAcceptedAsIs": "% aceptado sin cambios",
  "admin.quality.avgRefinements": "Ajustes medios",
  "admin.quality.overall": "Total",
  "admin.quality.empty": "Aún no hay métricas de calidad.",
  "admin.sla.title": "SLA de revisión por abogado",
  "admin.sla.target": "SLA objetivo: {hours} h",
  "admin.sla.counsel": "Abogado",
  "admin.sla.pending": "Pendientes",
  "admin.sla.avgHours": "Horas medias de respuesta",
  "admin.sla.pastSla": "Fuera de SLA",
  "admin.sla.reminders": "Recordatorios",
  "admin.sla.escalations": "Escalados",
  "admin.sla.empty": "Aún no hay datos de SLA.",
} as const;

export type DictKey = keyof typeof es;

/* ------------------------------------------------------------------ */
/* English (complete)                                                  */
/* ------------------------------------------------------------------ */

const en: Record<DictKey, string> = {
  "app.name": "Lol-AI-lo",
  "app.tagline": "Fund documentation, generated and validated",

  "common.loading": "Loading…",
  "common.error": "Something went wrong. Please try again.",
  "common.cancel": "Cancel",
  "common.confirm": "Confirm",
  "common.save": "Save",
  "common.edit": "Edit",
  "common.back": "Back",
  "common.actions": "Actions",
  "common.download": "Download",
  "common.upload": "Upload",
  "common.search": "Search",
  "common.all": "All",
  "common.empty": "No results.",
  "common.status": "Status",
  "common.date": "Date",
  "common.fund": "Fund",
  "common.docType": "Document type",
  "common.language": "Language",
  "common.email": "Email",
  "common.password": "Password",
  "common.name": "Name",
  "common.role": "Role",
  "common.logout": "Sign out",
  "common.optional": "optional",
  "common.notAvailable": "Not available",

  "role.client": "Client (fund)",
  "role.counsel": "Counsel (lawyer)",
  "role.admin": "Administrator",

  "dev.banner": "Development mode: Supabase is not configured. Stub session active.",
  "dev.bannerRole": "Simulated role:",
  "dev.chooseRole": "Choose a role to enter (development mode)",
  "dev.enterAs": "Enter as {role}",

  "nav.dashboard": "Dashboard",
  "nav.newRequest": "New request",
  "nav.documents": "Documents",
  "nav.counselQueue": "Reviews",
  "nav.gestoras": "Management companies",
  "nav.precedents": "Precedents",
  "nav.users": "Users",
  "nav.quality": "Quality & SLA",

  "auth.loginTitle": "Sign in",
  "auth.loginSubtitle": "Access your fund documentation workspace.",
  "auth.signIn": "Sign in",
  "auth.signupTitle": "Create account",
  "auth.signupSubtitle":
    "Your account role and management company are assigned by the service administrator.",
  "auth.signUp": "Sign up",
  "auth.noAccount": "Don't have an account?",
  "auth.hasAccount": "Already have an account?",
  "auth.goSignup": "Sign up",
  "auth.goLogin": "Sign in",
  "auth.signupDisabledStub":
    "Sign-up is unavailable in development mode. Use the login screen to pick a simulated role.",
  "auth.signupSuccess": "Account created. Check your inbox to confirm your address.",
  "auth.invalidCredentials": "Invalid credentials.",

  "status.parsing": "Parsing",
  "status.confirmed": "Confirmed",
  "status.generating": "Generating",
  "status.review_pending": "Pending review",
  "status.counsel_review": "Under counsel review",
  "status.validated": "Validated",
  "status.delivered": "Delivered",

  "dashboard.title": "My requests",
  "dashboard.subtitle": "Status of your document requests.",
  "dashboard.empty": "You haven't created any requests yet.",
  "dashboard.cta": "New request",
  "dashboard.viewDocument": "View document",

  "intake.title": "New document request",
  "intake.subtitle":
    "Describe the document you need. Our engine will generate it from your management company's precedents.",
  "intake.fund": "Fund",
  "intake.fundPlaceholder": "Select a fund",
  "intake.docType": "Document type",
  "intake.docTypePlaceholder": "Select a document type",
  "intake.docTypeCustom": "Describe the document type",
  "intake.docTypeCustomPlaceholder": "E.g., co-investment agreement",
  "intake.freetext": "Request description",
  "intake.freetextPlaceholder":
    "Describe the document: parties involved, dates, amounts, special conditions…",
  "intake.freetextPlaceholderStructured":
    "Additional context, special conditions…",
  "intake.structuredHeading": "Key document details",
  "intake.structuredHint":
    "These values are incorporated into the document as confirmed data and raise parsing accuracy.",
  "intake.partyPlaceholder": "Name of the person or entity",
  "intake.selectPlaceholder": "Select an option",
  "intake.charCount": "{count} / {max} characters",
  "intake.minChars": "Minimum {min} characters.",
  "intake.counselToggle": "Lawyer validation",
  "intake.counselHint":
    "A Lol-AI-lo Legal SLP lawyer will review and validate the document before delivery.",
  "intake.assignedCounsel": "Assigned counsel",
  "intake.turnaround": "Estimated review turnaround: {hours} business hours",
  "intake.noAssignedCounsel":
    "A lawyer from the Lol-AI-lo Legal SLP team will be assigned to your request.",
  "intake.submit": "Generar Documento →",

  "flow.parsing": "Analyzing your request…",
  "flow.parsingHint": "Extracting parties, dates and key terms.",
  "flow.generating": "Generating document…",
  "flow.generatingHint":
    "Retrieving precedents and drafting the document. This can take up to 60 seconds.",
  "flow.generationFailed": "Document generation failed.",
  "flow.generationFailedHint":
    "You can retry the generation. If the problem persists, contact support.",
  "flow.retry": "Reintentar",

  "params.title": "Parameter review",
  "params.subtitle":
    "We extracted these parameters from your request. Review and correct them before generating.",
  "params.summary": "Summary",
  "params.docTypeConfirmed": "Detected document type",
  "params.languageDetected": "Detected language",
  "params.parties": "Parties",
  "params.partyRole": "Role",
  "params.partyName": "Name",
  "params.keyDates": "Key dates",
  "params.jurisdiction": "Jurisdiction",
  "params.governingLaw": "Governing law",
  "params.keyTerms": "Key terms",
  "params.confidence": "Parse confidence",
  "params.unclearBadge": "[UNCLEAR]",
  "params.unclearHint":
    "Fields marked [UNCLEAR] have low confidence. Edit them to continue.",
  "params.notReady": "The request is not ready for generation. Review the flagged fields.",
  "params.unclassifiable": VERBATIM_UNCLASSIFIABLE,
  "params.confirm": "Confirmar y Generar",
  "params.editedNote": "Parameter edits are recorded in the audit log.",
  "params.backToIntake": "Rephrase request",
  "params.confirmedChip": "confirmed",

  "docfields.importe_total": "Total amount",
  "docfields.fecha_limite_pago": "Payment deadline",
  "docfields.porcentaje_compromiso": "Percentage of commitment",
  "docfields.numero_llamada": "Call number",
  "docfields.importe": "Amount",
  "docfields.fecha": "Date",
  "docfields.concepto": "Concept / origin",
  "docfields.contraparte": "Counterparty",
  "docfields.duracion_meses": "Duration (months)",
  "docfields.modalidad": "Unilateral or mutual",
  "docfields.fecha_reunion": "Meeting date",
  "docfields.asistentes": "Attendees",
  "docfields.acuerdos_principales": "Main resolutions",
  "docfields.persona": "Person",
  "docfields.cargo": "Position",
  "docfields.tipo": "Type",
  "docfields.fecha_efecto": "Effective date",
  "docfields.apoderado": "Attorney-in-fact",
  "docfields.facultades": "Powers granted",
  "docfields.vigencia": "Validity (end date)",
  "docfields.compania_objetivo": "Target company",
  "docfields.importe_inversion": "Investment amount",
  "docfields.valoracion_premoney": "Pre-money valuation",
  "docfields.tipo_instrumento": "Instrument type",
  "docfields.inversor": "Investor",
  "docfields.derechos_solicitados": "Requested rights",
  "docfields.fecha_referencia": "Reference date",
  "docfields.nueva_fecha": "New date",
  "docfields.justificacion": "Justification",

  "viewer.title": "Generated document",
  "viewer.downloadDraft": "Descargar Borrador",
  "viewer.downloadRedline": "Descargar Redline vs. Precedente",
  "viewer.exitATitle": "Me vale",
  "viewer.exitADesc":
    "Download the document now, without lawyer review, at your own responsibility.",
  "viewer.exitAAck": VERBATIM_EXIT_A_ACK,
  "viewer.exitAConfirm": "Confirmar y Descargar",
  "viewer.exitBTitle": "Lawyer validation",
  "viewer.exitBDesc":
    "A Lol-AI-lo Legal SLP lawyer will review the document and deliver it validated.",
  "viewer.exitBRequest": "Solicitar Validación",
  "viewer.exitBRequested":
    "Validation requested. You will receive an email when the document is validated.",
  "viewer.level3Warning": VERBATIM_LEVEL3_WARNING,
  "viewer.missingBlocksExitA":
    "The document contains unfilled [MISSING] fields. Direct download (Exit A) is blocked: lawyer validation is required.",
  "viewer.disclaimer": VERBATIM_SLP_DISCLAIMER,
  "viewer.deliveredNote":
    "Document delivered. It becomes a precedent candidate, pending admin approval.",
  "viewer.validatedNote":
    "Document validated by counsel and delivered. It has been added automatically to the precedent library.",
  "viewer.counselReviewNote":
    "The document is under counsel review. We'll email you once it's validated.",
  "viewer.notReadyYet": "The document is not available yet.",
  "viewer.fallbackLevel": "Precedent level",
  "viewer.requestMeta": "Request details",
  "viewer.tabDraft": "Draft",
  "viewer.tabRedline": "Redline vs. Precedent",
  "viewer.versionLabel": "Version",
  "viewer.oldVersionBanner":
    "You are viewing a previous version of the document. Go back to the latest version to download, request adjustments or continue with delivery.",

  "refine.title": "Solicitar ajuste",
  "refine.desc":
    "Describe the change you need in plain language (e.g., “change the notice period to 15 days”). We will regenerate the document applying it, keeping the version history.",
  "refine.placeholder": "E.g., change the notice period to 15 calendar days…",
  "refine.remaining": "You have {count} adjustments left",
  "refine.submit": "Solicitar ajuste",
  "refine.processing": "Applying adjustment…",
  "refine.processingHint":
    "Regenerating the document with your adjustment. This can take up to 60 seconds.",
  "refine.applied": "Adjustment applied. Showing the new version.",
  "refine.failed": "We could not apply the adjustment.",
  "refine.limitReached":
    "You have used all available adjustments. For further changes, use “Solicitar Validación” (lawyer validation).",

  "htmlViewer.loading": "Loading document…",
  "htmlViewer.error": "The document could not be loaded. Please try again.",
  "htmlViewer.legend": "{ins} insertions · {del} deletions",

  "documents.title": "Document history",
  "documents.subtitle": "All your requests and generated documents.",
  "documents.filterStatus": "Status",
  "documents.filterDocType": "Document type",
  "documents.filterFund": "Fund",
  "documents.empty": "No documents match the filters.",
  "documents.open": "Open",

  "counsel.queueTitle": "Review queue",
  "counsel.queueSubtitle": "Documents pending lawyer validation (Exit B).",
  "counsel.queueEmpty": "No pending reviews.",
  "counsel.requestedBy": "Requested by",
  "counsel.review": "Review",
  "counsel.slaChip": "{hours} h / {sla} h SLA",
  "counsel.slaExceeded": "SLA exceeded · {hours} h",
  "counsel.reviewTitle": "Document review",
  "counsel.draftPane": "Draft",
  "counsel.redlinePane": "Redline vs. Precedent",
  "counsel.editorTitle": "Counsel editor",
  "counsel.editorHint":
    "Edit the text directly. Changes are saved as a counsel version (counsel_edit).",
  "counsel.editorPlaceholder": "The draft text will appear here…",
  "counsel.saveEdit": "Save edit",
  "counsel.editSaved": "Edit saved.",
  "counsel.comments": "Comments",
  "counsel.noComments": "No comments.",
  "counsel.addComment": "Add comment",
  "counsel.commentPlaceholder": "Write a comment or flag an issue…",
  "counsel.downloadDocx": "Download .docx",
  "counsel.uploadDocx": "Upload edited .docx",
  "counsel.uploadDone": "File uploaded as counsel version.",
  "counsel.validate": "Validar y Entregar",
  "counsel.validatedOk":
    "Document validated and delivered to the client. It has been added to the precedent library.",

  "admin.gestoras.title": "Management companies",
  "admin.gestoras.subtitle":
    "Management companies onboarded on the platform. Data is siloed per gestora.",
  "admin.gestoras.new": "New gestora",
  "admin.gestoras.name": "Name",
  "admin.gestoras.tier": "Plan",
  "admin.gestoras.billingEmail": "Billing email",
  "admin.gestoras.funds": "Funds",
  "admin.gestoras.create": "Create gestora",
  "admin.gestoras.created": "Gestora created.",

  "admin.counsel.title": "Assigned counsel",
  "admin.counsel.subtitle":
    "Assign lawyers to each management company. Validation (Exit B) notifications go to the primary counsel; with no assignment, to all counsel users.",
  "admin.counsel.assign": "Assign counsel",
  "admin.counsel.selectCounsel": "Select a lawyer",
  "admin.counsel.primary": "Primary",
  "admin.counsel.backup": "Backup",
  "admin.counsel.makePrimary": "Make primary",
  "admin.counsel.remove": "Remove",
  "admin.counsel.empty":
    "No counsel assigned: notifications are sent to all counsel users.",
  "admin.counsel.assigned": "Counsel assigned.",
  "admin.counsel.removed": "Assignment removed.",

  "tier.starter": "Starter",
  "tier.growth": "Growth",
  "tier.custom": "Custom",

  "admin.precedents.title": "Precedent library",
  "admin.precedents.subtitle":
    "Per-gestora precedents with version control. Only active versions are generation bases.",
  "admin.precedents.upload": "Upload precedent",
  "admin.precedents.uploadHint":
    "Only .docx can be a generation base; PDFs are indexed as RAG reference only.",
  "admin.precedents.uploaded": "Precedent uploaded (draft version).",
  "admin.precedents.version": "Version",
  "admin.precedents.ragWeight": "RAG weight",
  "admin.precedents.activate": "Activate",
  "admin.precedents.supersede": "Supersede",
  "admin.precedents.source": "Source",
  "precedentStatus.draft": "Draft",
  "precedentStatus.active": "Active",
  "precedentStatus.superseded": "Superseded",
  "precedentSource.manual_upload": "Manual upload",
  "precedentSource.validated_output": "Validated output",
  "precedentSource.slp_curated": "SLP curated",
  "precedentSource.platform_base": "Platform base",

  "admin.users.title": "Users",
  "admin.users.subtitle": "Platform users and their roles.",
  "admin.users.invite": "Invite user",
  "admin.users.gestora": "Management company",
  "admin.users.invited": "Invitation sent.",

  "admin.quality.title": "Quality & SLA",
  "admin.quality.subtitle":
    "Generation quality (how much counsel changes the AI draft) and counsel review SLA compliance.",
  "admin.quality.qualityTitle": "Quality by document type",
  "admin.quality.qualityHint":
    "Similarity 1.00 = document delivered with no changes versus the AI draft.",
  "admin.quality.count": "Docs",
  "admin.quality.avgSimilarity": "Avg. similarity",
  "admin.quality.pctAcceptedAsIs": "% accepted as-is",
  "admin.quality.avgRefinements": "Avg. adjustments",
  "admin.quality.overall": "Total",
  "admin.quality.empty": "No quality metrics yet.",
  "admin.sla.title": "Counsel review SLA",
  "admin.sla.target": "Target SLA: {hours} h",
  "admin.sla.counsel": "Counsel",
  "admin.sla.pending": "Pending",
  "admin.sla.avgHours": "Avg. response hours",
  "admin.sla.pastSla": "Past SLA",
  "admin.sla.reminders": "Reminders",
  "admin.sla.escalations": "Escalations",
  "admin.sla.empty": "No SLA data yet.",
};

/* ------------------------------------------------------------------ */
/* French / German shells — fall back to Spanish                        */
/* ------------------------------------------------------------------ */

const fr: Partial<Record<DictKey, string>> = {
  "app.name": "Lol-AI-lo",
  "app.tagline": "Documentation de fonds, générée et validée",
  "common.loading": "Chargement…",
  "common.logout": "Se déconnecter",
  "nav.dashboard": "Tableau de bord",
  "nav.newRequest": "Nouvelle demande",
  "nav.documents": "Documents",
  "auth.loginTitle": "Connexion",
  "auth.signIn": "Se connecter",
  // TODO: complete French dictionary before FR launch (i18n shell only).
};

const de: Partial<Record<DictKey, string>> = {
  "app.name": "Lol-AI-lo",
  "app.tagline": "Fondsdokumentation, generiert und validiert",
  "common.loading": "Wird geladen…",
  "common.logout": "Abmelden",
  "nav.dashboard": "Übersicht",
  "nav.newRequest": "Neue Anfrage",
  "nav.documents": "Dokumente",
  "auth.loginTitle": "Anmelden",
  "auth.signIn": "Anmelden",
  // TODO: complete German dictionary before DE launch (i18n shell only).
};

const DICTIONARIES: Record<Locale, Partial<Record<DictKey, string>>> = {
  es,
  en,
  fr,
  de,
};

/** Translate a key in the given locale, with {var} interpolation and es fallback. */
export function translate(
  locale: Locale,
  key: DictKey,
  vars?: Record<string, string | number>,
): string {
  let text: string = DICTIONARIES[locale]?.[key] ?? es[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.split(`{${k}}`).join(String(v));
    }
  }
  return text;
}
