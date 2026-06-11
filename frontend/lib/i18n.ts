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
  "intake.charCount": "{count} / {max} caracteres",
  "intake.minChars": "Mínimo {min} caracteres.",
  "intake.counselToggle": "Validación por abogado",
  "intake.counselHint":
    "Un abogado de Lol-AI-lo Legal SLP revisará y validará el documento antes de su entrega.",
  "intake.assignedCounsel": "Abogado asignado",
  "intake.turnaround": "Plazo estimado de revisión: {hours} h laborables",
  "intake.submit": "Generar Documento →",

  // Flow
  "flow.parsing": "Analizando tu solicitud…",
  "flow.parsingHint": "Extrayendo partes, fechas y términos clave.",
  "flow.generating": "Generando documento…",
  "flow.generatingHint":
    "Recuperando precedentes y redactando el borrador. Puede tardar hasta 60 segundos.",

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
  "intake.charCount": "{count} / {max} characters",
  "intake.minChars": "Minimum {min} characters.",
  "intake.counselToggle": "Lawyer validation",
  "intake.counselHint":
    "A Lol-AI-lo Legal SLP lawyer will review and validate the document before delivery.",
  "intake.assignedCounsel": "Assigned counsel",
  "intake.turnaround": "Estimated review turnaround: {hours} business hours",
  "intake.submit": "Generar Documento →",

  "flow.parsing": "Analyzing your request…",
  "flow.parsingHint": "Extracting parties, dates and key terms.",
  "flow.generating": "Generating document…",
  "flow.generatingHint":
    "Retrieving precedents and drafting the document. This can take up to 60 seconds.",

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
