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
  "nav.billing": "Facturación",
  "nav.account": "Mi cuenta",
  "nav.modelConfig": "Modelo por gestora",

  // Collaboration / sharing
  "share.button": "Compartir",
  "share.title": "Compartir con tu equipo",
  "share.note":
    "Los colegas de tu gestora con acceso podrán ver y descargar, pero no realizar acciones (validación, ajustes o borrado).",
  "share.addColleague": "Añadir colega",
  "share.selectColleague": "Selecciona un colega…",
  "share.add": "Añadir",
  "share.collaborators": "Con acceso",
  "share.empty": "Aún no lo has compartido con nadie.",
  "share.viewer": "Lectura",
  "share.remove": "Quitar",
  "share.sharedWithYou": "Compartido contigo",
  "share.sharedByYou": "Compartido por {who}",

  // Account — security (MFA)
  "account.security.title": "Seguridad de la cuenta",
  "account.security.subtitle":
    "Protege tu cuenta con verificación en dos pasos (TOTP).",
  "account.security.mfaStatus": "Verificación en dos pasos",
  "account.security.mfaOn": "Activada",
  "account.security.mfaOff": "Desactivada",
  "account.security.enable": "Activar 2FA",
  "account.security.disable": "Desactivar 2FA",
  "account.security.enroll":
    "Escanea el código en tu app de autenticación e introduce el código de 6 dígitos.",
  "account.security.code": "Código de 6 dígitos",
  "account.security.verify": "Verificar y activar",
  "account.security.devNotice":
    "La verificación en dos pasos usa Supabase Auth y no está disponible en modo desarrollo. Aquí puedes alternar el estado de demostración.",
  "account.security.demoToggle": "Estado de demostración",

  // Account — privacy (GDPR subject rights)
  "account.privacy.title": "Privacidad y mis datos",
  "account.privacy.subtitle":
    "Ejercita tus derechos de acceso y supresión (RGPD arts. 15, 17 y 20).",
  "account.privacy.export": "Descargar mis datos",
  "account.privacy.exportHint":
    "Obtén una copia en JSON de tu perfil y tus solicitudes.",
  "account.privacy.delete": "Eliminar mis datos",
  "account.privacy.deleteHint":
    "El registro de auditoría se conserva por obligación legal; el resto de tus datos se anonimiza o elimina.",
  "account.privacy.mode": "Modo",
  "account.privacy.modeAnonymize": "Anonimizar (conservar registros sin PII)",
  "account.privacy.modeErase": "Eliminar mis solicitudes y documentos",
  "account.privacy.confirmLabel":
    'Escribe "{phrase}" para confirmar',
  "account.privacy.confirmCta": "Eliminar definitivamente",
  "account.privacy.deleted": "Solicitud de supresión registrada.",

  // Admin — per-gestora model configuration
  "modelconfig.title": "Modelo por gestora",
  "modelconfig.subtitle":
    "Sobrescribe el proveedor, el modelo y las claves (cifradas) por gestora. Por defecto se usan los valores globales de la plataforma.",
  "modelconfig.gestora": "Gestora",
  "modelconfig.llmProvider": "Proveedor LLM",
  "modelconfig.llmModel": "Modelo LLM",
  "modelconfig.embeddingProvider": "Proveedor de embeddings",
  "modelconfig.embeddingModel": "Modelo de embeddings",
  "modelconfig.ollamaBaseUrl": "URL de Ollama",
  "modelconfig.anthropicKey": "Clave Anthropic",
  "modelconfig.mistralKey": "Clave Mistral (UE)",
  "modelconfig.openaiKey": "Clave OpenAI",
  "modelconfig.keySet": "Configurada",
  "modelconfig.keyUnset": "No configurada",
  "modelconfig.keyPlaceholderSet": "•••••••• (déjalo vacío para mantener)",
  "modelconfig.keyClear": "Vaciar para borrar la clave",
  "modelconfig.usingDefault": "Usando los valores globales de la plataforma",
  "modelconfig.usingCustom": "Configuración personalizada",
  "modelconfig.inherit": "(heredar global)",
  "modelconfig.save": "Guardar configuración",
  "modelconfig.saved": "Configuración guardada.",

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
  "intake.newFund": "+ Añadir fondo o vehículo",
  "intake.newFundName": "Nombre del fondo/vehículo",
  "intake.newFundJurisdiction": "Jurisdicción",
  "intake.newFundCreate": "Crear fondo",
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

  // Admin — GDPR data retention (per gestora)
  "admin.retention.title": "Política de retención de datos",
  "admin.retention.subtitle":
    "Meses que se conservan los documentos de solicitudes entregadas. Pasado el plazo, el barrido de retención elimina los archivos; el registro de auditoría se conserva siempre (RGPD).",
  "admin.retention.months": "Retención (meses)",
  "admin.retention.hint": "Entre 6 y 120 meses.",
  "admin.retention.default": "Valor por defecto de la plataforma",
  "admin.retention.custom": "Política personalizada",
  "admin.retention.save": "Guardar política",
  "admin.retention.saved": "Política de retención guardada.",
  "admin.retention.invalid": "Indica un valor entre 6 y 120 meses.",

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
  "precedentSource.gestora_model": "Modelo de gestora",

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

  // Admin — billing over usage_events (improvement #7)
  "admin.billing.title": "Facturación",
  "admin.billing.subtitle":
    "Consumo mensual por gestora: documentos generados, límites del plan y exceso estimado.",
  "admin.billing.period": "Periodo",
  "admin.billing.exportCsv": "Exportar CSV",
  "admin.billing.gestora": "Gestora",
  "admin.billing.tier": "Plan",
  "admin.billing.docs": "Docs generados / límite",
  "admin.billing.overage": "Exceso",
  "admin.billing.exitA": "Exit A",
  "admin.billing.exitB": "Exit B (sol. / val.)",
  "admin.billing.overageEur": "€ exceso est.",
  "admin.billing.funds": "Fondos",
  "admin.billing.unlimited": "Ilimitado",
  "admin.billing.overFunds": "Supera el límite de fondos del plan",
  "admin.billing.empty": "No hay datos de consumo para este periodo.",
  "admin.billing.pricesTbdHint":
    "El € estimado es 0 mientras los precios de exceso no estén configurados.",

  // Client dashboard — consumption widget (improvement #7)
  "dashboard.usageTitle": "Consumo del plan",
  "dashboard.usage": "Este mes: {used} de {limit} documentos",
  "dashboard.usageUnlimited": "Este mes: {used} documentos · plan sin límite",

  // Nav — drafting-agents admin pages
  "nav.playbooks": "Playbooks",
  "nav.lessons": "Lecciones",

  // Drafting branches (specialized drafter agents)
  "branch.gobierno_corporativo": "Gobierno Corporativo",
  "branch.operaciones_de_fondo": "Operaciones de Fondo",
  "branch.gestion_de_portfolio": "Gestión de Portfolio",
  "branch.cumplimiento_regulatorio": "Cumplimiento y Regulatorio",
  "branch.contratos_terceros": "Contratos con Terceros",
  "branch.generic": "General",
  "branch.badge": "Agente: {branch}",

  // Internal automated review (critic) — client + counsel
  "review.title": "Revisión interna automática",
  "review.loading": "Cargando revisión interna…",
  "review.none": "Sin revisión automática.",
  "review.error": "No se ha podido cargar la revisión interna.",
  "review.approved": "Revisión interna: aprobada",
  "review.fixed": "{count} observación corregida",
  "review.fixedPlural": "{count} observaciones corregidas",
  "review.forcedCounsel": "Revisión interna: derivado a abogado",
  "review.round": "Ronda {n}",
  "review.roundApproved": "Aprobada",
  "review.roundIssues": "{count} observación",
  "review.roundIssuesPlural": "{count} observaciones",
  "review.showDetails": "Ver detalle",
  "review.hideDetails": "Ocultar detalle",
  "review.problem": "Problema",
  "review.suggestedFix": "Corrección sugerida",
  "review.confidence": "Confianza",
  "review.location": "Ubicación",
  "review.citationWhere": "En el borrador",
  "review.severity.blocking": "Bloqueante",
  "review.severity.major": "Importante",
  "review.severity.minor": "Menor",
  "review.category.factual": "Factual",
  "review.category.completeness": "Completitud",
  "review.category.legal": "Legal",
  "review.category.consistency": "Consistencia",

  // Admin — Modelos (gestora master templates)
  "admin.models.title": "Modelos",
  "admin.models.subtitle":
    "Plantillas maestras de la gestora (modelos). Tienen prioridad sobre los precedentes como base de generación.",
  "admin.models.tabModels": "Modelos",
  "admin.models.tabPrecedents": "Precedentes",
  "admin.models.upload": "Subir modelo",
  "admin.models.uploadHint":
    "El modelo maestro de la gestora es la base preferente de generación (por encima de los precedentes).",
  "admin.models.uploaded": "Modelo subido (versión en borrador).",
  "admin.models.empty": "Esta gestora aún no tiene modelos maestros.",

  // Admin — Playbooks (review rules CRUD)
  "admin.playbooks.title": "Playbooks de revisión",
  "admin.playbooks.subtitle":
    "Reglas de revisión redactadas por humanos que el revisor automático aplica. Aisladas por gestora.",
  "admin.playbooks.selectGestora": "Selecciona una gestora",
  "admin.playbooks.create": "Nuevo playbook",
  "admin.playbooks.edit": "Editar playbook",
  "admin.playbooks.titleField": "Título",
  "admin.playbooks.content": "Contenido (reglas)",
  "admin.playbooks.contentHint":
    "Este texto se inyecta literalmente en el revisor automático.",
  "admin.playbooks.branch": "Rama (opcional)",
  "admin.playbooks.docType": "Tipo de documento (opcional)",
  "admin.playbooks.anyBranch": "Todas las ramas",
  "admin.playbooks.anyDocType": "Todos los tipos",
  "admin.playbooks.file": "Adjunto (opcional .docx / .pdf)",
  "admin.playbooks.activeOnly": "Activos",
  "admin.playbooks.inactive": "Inactivos",
  "admin.playbooks.active": "Activo",
  "admin.playbooks.scope": "Ámbito",
  "admin.playbooks.scopeAll": "Toda la gestora",
  "admin.playbooks.activate": "Activar",
  "admin.playbooks.deactivate": "Desactivar",
  "admin.playbooks.delete": "Eliminar",
  "admin.playbooks.deleteConfirm": "¿Eliminar este playbook?",
  "admin.playbooks.created": "Playbook creado.",
  "admin.playbooks.updated": "Playbook actualizado.",
  "admin.playbooks.empty": "Esta gestora aún no tiene playbooks.",
  "admin.playbooks.save": "Guardar playbook",
  "admin.playbooks.cancel": "Cancelar",
  "admin.playbooks.hasFile": "Con adjunto",

  // Admin — Lecciones (drafting lessons, read-only)
  "admin.lessons.title": "Lecciones aprendidas",
  "admin.lessons.subtitle":
    "Reglas de redacción que el agente de cada gestora ha aprendido de los documentos validados.",
  "admin.lessons.siloNote":
    "Las lecciones están aisladas por gestora: nunca se comparten entre gestoras.",
  "admin.lessons.selectGestora": "Selecciona una gestora",
  "admin.lessons.filterBranch": "Filtrar por rama",
  "admin.lessons.allBranches": "Todas las ramas",
  "admin.lessons.branch": "Rama",
  "admin.lessons.docType": "Tipo de documento",
  "admin.lessons.weight": "Peso",
  "admin.lessons.lesson": "Lección",
  "admin.lessons.empty": "Esta gestora aún no ha aprendido lecciones.",

  // Tabular Review (010_tabular_reviews.sql)
  "nav.tabular": "Revisión tabular",
  "tabular.title": "Revisión tabular",
  "tabular.subtitle":
    "Extrae datos de varios documentos a la vez en una tabla, con citas verificables.",
  "tabular.new": "Nueva revisión",
  "tabular.empty": "Aún no has creado ninguna revisión tabular.",
  "tabular.open": "Abrir",
  "tabular.column": "Columna",
  "tabular.columns": "Columnas",
  "tabular.document": "Documento",
  "tabular.documents": "Documentos",
  "tabular.cells": "Celdas",
  "tabular.run": "Ejecutar extracción",
  "tabular.running": "Extrayendo…",
  "tabular.exportCsv": "Exportar CSV",
  "tabular.addColumn": "Añadir columna",
  "tabular.removeColumn": "Eliminar columna",
  "tabular.removeDocument": "Eliminar documento",
  "tabular.progress": "{done} de {total} celdas",
  "tabular.errorCount": "{count} con error",
  "tabular.citation": "Cita",
  "tabular.citationPage": "Página {page}",
  "tabular.citationNoPage": "Sin paginación (texto plano)",
  "tabular.reasoning": "Razonamiento",
  "tabular.cellPending": "Pendiente",
  "tabular.cellError": "Error",
  "tabular.cellEmpty": "—",
  "tabular.notFound": "No encontrado",
  // New-review flow
  "tabular.newTitle": "Nueva revisión tabular",
  "tabular.newSubtitle":
    "Da un título, elige documentos de tu gestora y define las columnas a extraer.",
  "tabular.fieldTitle": "Título",
  "tabular.fieldTitlePlaceholder": "p. ej. Comparativa de actas de consejo",
  "tabular.fieldFund": "Fondo (opcional)",
  "tabular.pickDocuments": "Selecciona documentos",
  "tabular.pickDocumentsHint":
    "Solo se muestran documentos de tu propia gestora.",
  "tabular.noDocuments": "No hay documentos disponibles para seleccionar.",
  "tabular.defineColumns": "Define las columnas",
  "tabular.columnName": "Nombre de la columna",
  "tabular.columnQuestion": "Pregunta",
  "tabular.columnType": "Tipo de respuesta",
  "tabular.columnOptions": "Opciones (separadas por comas)",
  "tabular.addColumnRow": "Añadir otra columna",
  "tabular.create": "Crear revisión",
  "tabular.createAndRun": "Crear y ejecutar",
  "tabular.needTitle": "Indica un título.",
  "tabular.needDocuments": "Selecciona al menos un documento.",
  "tabular.needColumns": "Define al menos una columna con su pregunta.",
  // Column types
  "coltype.text": "Texto",
  "coltype.number": "Número",
  "coltype.percent": "Porcentaje",
  "coltype.monetary": "Importe monetario",
  "coltype.date": "Fecha",
  "coltype.yes_no": "Sí / No",
  "coltype.tag": "Etiqueta (opciones)",
  // Tabular statuses
  "tabularStatus.draft": "Borrador",
  "tabularStatus.running": "En ejecución",
  "tabularStatus.complete": "Completada",
  "tabularStatus.failed": "Fallida",
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
  "nav.billing": "Billing",
  "nav.account": "My account",
  "nav.modelConfig": "Model per gestora",

  // Collaboration / sharing
  "share.button": "Share",
  "share.title": "Share with your team",
  "share.note":
    "Colleagues from your gestora with access can view and download, but not take actions (validation, refinements or deletion).",
  "share.addColleague": "Add colleague",
  "share.selectColleague": "Select a colleague…",
  "share.add": "Add",
  "share.collaborators": "With access",
  "share.empty": "Not shared with anyone yet.",
  "share.viewer": "Viewer",
  "share.remove": "Remove",
  "share.sharedWithYou": "Shared with you",
  "share.sharedByYou": "Shared by {who}",

  // Account — security (MFA)
  "account.security.title": "Account security",
  "account.security.subtitle":
    "Protect your account with two-factor authentication (TOTP).",
  "account.security.mfaStatus": "Two-factor authentication",
  "account.security.mfaOn": "Enabled",
  "account.security.mfaOff": "Disabled",
  "account.security.enable": "Enable 2FA",
  "account.security.disable": "Disable 2FA",
  "account.security.enroll":
    "Scan the code in your authenticator app and enter the 6-digit code.",
  "account.security.code": "6-digit code",
  "account.security.verify": "Verify and enable",
  "account.security.devNotice":
    "Two-factor authentication uses Supabase Auth and is unavailable in development mode. You can toggle the demo state here.",
  "account.security.demoToggle": "Demo state",

  // Account — privacy (GDPR subject rights)
  "account.privacy.title": "Privacy and my data",
  "account.privacy.subtitle":
    "Exercise your access and erasure rights (GDPR arts. 15, 17 and 20).",
  "account.privacy.export": "Download my data",
  "account.privacy.exportHint":
    "Get a JSON copy of your profile and your requests.",
  "account.privacy.delete": "Delete my data",
  "account.privacy.deleteHint":
    "The audit log is retained as legally required; the rest of your data is anonymised or erased.",
  "account.privacy.mode": "Mode",
  "account.privacy.modeAnonymize": "Anonymise (keep records without PII)",
  "account.privacy.modeErase": "Erase my requests and documents",
  "account.privacy.confirmLabel": 'Type "{phrase}" to confirm',
  "account.privacy.confirmCta": "Delete permanently",
  "account.privacy.deleted": "Erasure request recorded.",

  // Admin — per-gestora model configuration
  "modelconfig.title": "Model per gestora",
  "modelconfig.subtitle":
    "Override the provider, model and (encrypted) keys per gestora. Platform-wide defaults are used otherwise.",
  "modelconfig.gestora": "Gestora",
  "modelconfig.llmProvider": "LLM provider",
  "modelconfig.llmModel": "LLM model",
  "modelconfig.embeddingProvider": "Embedding provider",
  "modelconfig.embeddingModel": "Embedding model",
  "modelconfig.ollamaBaseUrl": "Ollama URL",
  "modelconfig.anthropicKey": "Anthropic key",
  "modelconfig.mistralKey": "Mistral key (EU)",
  "modelconfig.openaiKey": "OpenAI key",
  "modelconfig.keySet": "Set",
  "modelconfig.keyUnset": "Not set",
  "modelconfig.keyPlaceholderSet": "•••••••• (leave blank to keep)",
  "modelconfig.keyClear": "Clear to remove the key",
  "modelconfig.usingDefault": "Using platform-wide defaults",
  "modelconfig.usingCustom": "Custom configuration",
  "modelconfig.inherit": "(inherit global)",
  "modelconfig.save": "Save configuration",
  "modelconfig.saved": "Configuration saved.",

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
  "intake.newFund": "+ Add fund or vehicle",
  "intake.newFundName": "Fund/vehicle name",
  "intake.newFundJurisdiction": "Jurisdiction",
  "intake.newFundCreate": "Create fund",
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
  "precedentSource.gestora_model": "Gestora model",

  "admin.users.title": "Users",
  "admin.users.subtitle": "Platform users and their roles.",
  "admin.users.invite": "Invite user",
  "admin.users.gestora": "Management company",
  "admin.users.invited": "Invitation sent.",

  // Admin — GDPR data retention (per gestora)
  "admin.retention.title": "Data retention policy",
  "admin.retention.subtitle":
    "How long delivered documents are kept for the selected gestora before the retention sweep removes them (audit trail is always preserved).",
  "admin.retention.months": "Retention (months)",
  "admin.retention.hint": "Between 6 and 120 months.",
  "admin.retention.default": "Platform default",
  "admin.retention.custom": "Custom policy",
  "admin.retention.save": "Save policy",
  "admin.retention.saved": "Retention policy saved.",
  "admin.retention.invalid": "Enter a value between 6 and 120 months.",

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

  "admin.billing.title": "Billing",
  "admin.billing.subtitle":
    "Monthly consumption per management company: documents generated, plan limits and estimated overage.",
  "admin.billing.period": "Period",
  "admin.billing.exportCsv": "Export CSV",
  "admin.billing.gestora": "Management company",
  "admin.billing.tier": "Plan",
  "admin.billing.docs": "Docs generated / limit",
  "admin.billing.overage": "Overage",
  "admin.billing.exitA": "Exit A",
  "admin.billing.exitB": "Exit B (req. / val.)",
  "admin.billing.overageEur": "Est. overage €",
  "admin.billing.funds": "Funds",
  "admin.billing.unlimited": "Unlimited",
  "admin.billing.overFunds": "Exceeds the plan's funds limit",
  "admin.billing.empty": "No consumption data for this period.",
  "admin.billing.pricesTbdHint":
    "The estimated € stays 0 while overage prices are not configured.",

  "dashboard.usageTitle": "Plan consumption",
  "dashboard.usage": "This month: {used} of {limit} documents",
  "dashboard.usageUnlimited": "This month: {used} documents · unlimited plan",

  // Nav — drafting-agents admin pages
  "nav.playbooks": "Playbooks",
  "nav.lessons": "Lessons",

  // Drafting branches (specialized drafter agents)
  "branch.gobierno_corporativo": "Corporate Governance",
  "branch.operaciones_de_fondo": "Fund Operations",
  "branch.gestion_de_portfolio": "Portfolio Management",
  "branch.cumplimiento_regulatorio": "Compliance & Regulatory",
  "branch.contratos_terceros": "Third-Party Contracts",
  "branch.generic": "General",
  "branch.badge": "Agent: {branch}",

  // Internal automated review (critic) — client + counsel
  "review.title": "Internal automated review",
  "review.loading": "Loading internal review…",
  "review.none": "No automated review.",
  "review.error": "Could not load the internal review.",
  "review.approved": "Internal review: approved",
  "review.fixed": "{count} issue fixed",
  "review.fixedPlural": "{count} issues fixed",
  "review.forcedCounsel": "Internal review: referred to counsel",
  "review.round": "Round {n}",
  "review.roundApproved": "Approved",
  "review.roundIssues": "{count} issue",
  "review.roundIssuesPlural": "{count} issues",
  "review.showDetails": "Show details",
  "review.hideDetails": "Hide details",
  "review.problem": "Problem",
  "review.suggestedFix": "Suggested fix",
  "review.confidence": "Confidence",
  "review.location": "Location",
  "review.citationWhere": "In the draft",
  "review.severity.blocking": "Blocking",
  "review.severity.major": "Major",
  "review.severity.minor": "Minor",
  "review.category.factual": "Factual",
  "review.category.completeness": "Completeness",
  "review.category.legal": "Legal",
  "review.category.consistency": "Consistency",

  // Admin — Models (gestora master templates)
  "admin.models.title": "Models",
  "admin.models.subtitle":
    "Gestora master templates (models). They outrank precedents as the generation base.",
  "admin.models.tabModels": "Models",
  "admin.models.tabPrecedents": "Precedents",
  "admin.models.upload": "Upload model",
  "admin.models.uploadHint":
    "The gestora master model is the preferred generation base (above precedents).",
  "admin.models.uploaded": "Model uploaded (draft version).",
  "admin.models.empty": "This gestora has no master models yet.",

  // Admin — Playbooks (review rules CRUD)
  "admin.playbooks.title": "Review playbooks",
  "admin.playbooks.subtitle":
    "Human-authored review rules the automated reviewer enforces. Siloed per gestora.",
  "admin.playbooks.selectGestora": "Select a gestora",
  "admin.playbooks.create": "New playbook",
  "admin.playbooks.edit": "Edit playbook",
  "admin.playbooks.titleField": "Title",
  "admin.playbooks.content": "Content (rules)",
  "admin.playbooks.contentHint":
    "This text is injected verbatim into the automated reviewer.",
  "admin.playbooks.branch": "Branch (optional)",
  "admin.playbooks.docType": "Document type (optional)",
  "admin.playbooks.anyBranch": "All branches",
  "admin.playbooks.anyDocType": "All types",
  "admin.playbooks.file": "Attachment (optional .docx / .pdf)",
  "admin.playbooks.activeOnly": "Active",
  "admin.playbooks.inactive": "Inactive",
  "admin.playbooks.active": "Active",
  "admin.playbooks.scope": "Scope",
  "admin.playbooks.scopeAll": "Whole gestora",
  "admin.playbooks.activate": "Activate",
  "admin.playbooks.deactivate": "Deactivate",
  "admin.playbooks.delete": "Delete",
  "admin.playbooks.deleteConfirm": "Delete this playbook?",
  "admin.playbooks.created": "Playbook created.",
  "admin.playbooks.updated": "Playbook updated.",
  "admin.playbooks.empty": "This gestora has no playbooks yet.",
  "admin.playbooks.save": "Save playbook",
  "admin.playbooks.cancel": "Cancel",
  "admin.playbooks.hasFile": "Has attachment",

  // Admin — Lessons (drafting lessons, read-only)
  "admin.lessons.title": "Learned lessons",
  "admin.lessons.subtitle":
    "Drafting rules each gestora's agent has learned from validated documents.",
  "admin.lessons.siloNote":
    "Lessons are siloed per gestora: they are never shared across gestoras.",
  "admin.lessons.selectGestora": "Select a gestora",
  "admin.lessons.filterBranch": "Filter by branch",
  "admin.lessons.allBranches": "All branches",
  "admin.lessons.branch": "Branch",
  "admin.lessons.docType": "Document type",
  "admin.lessons.weight": "Weight",
  "admin.lessons.lesson": "Lesson",
  "admin.lessons.empty": "This gestora has not learned any lessons yet.",

  // Tabular Review (010_tabular_reviews.sql)
  "nav.tabular": "Tabular review",
  "tabular.title": "Tabular review",
  "tabular.subtitle":
    "Extract data from several documents at once into a table, with verifiable citations.",
  "tabular.new": "New review",
  "tabular.empty": "You haven't created any tabular reviews yet.",
  "tabular.open": "Open",
  "tabular.column": "Column",
  "tabular.columns": "Columns",
  "tabular.document": "Document",
  "tabular.documents": "Documents",
  "tabular.cells": "Cells",
  "tabular.run": "Run extraction",
  "tabular.running": "Extracting…",
  "tabular.exportCsv": "Export CSV",
  "tabular.addColumn": "Add column",
  "tabular.removeColumn": "Remove column",
  "tabular.removeDocument": "Remove document",
  "tabular.progress": "{done} of {total} cells",
  "tabular.errorCount": "{count} with errors",
  "tabular.citation": "Citation",
  "tabular.citationPage": "Page {page}",
  "tabular.citationNoPage": "No pagination (plain text)",
  "tabular.reasoning": "Reasoning",
  "tabular.cellPending": "Pending",
  "tabular.cellError": "Error",
  "tabular.cellEmpty": "—",
  "tabular.notFound": "Not found",
  // New-review flow
  "tabular.newTitle": "New tabular review",
  "tabular.newSubtitle":
    "Give it a title, pick documents from your gestora, and define the columns to extract.",
  "tabular.fieldTitle": "Title",
  "tabular.fieldTitlePlaceholder": "e.g. Board minutes comparison",
  "tabular.fieldFund": "Fund (optional)",
  "tabular.pickDocuments": "Select documents",
  "tabular.pickDocumentsHint": "Only documents from your own gestora are shown.",
  "tabular.noDocuments": "No documents available to select.",
  "tabular.defineColumns": "Define the columns",
  "tabular.columnName": "Column name",
  "tabular.columnQuestion": "Question",
  "tabular.columnType": "Answer type",
  "tabular.columnOptions": "Options (comma-separated)",
  "tabular.addColumnRow": "Add another column",
  "tabular.create": "Create review",
  "tabular.createAndRun": "Create and run",
  "tabular.needTitle": "Please enter a title.",
  "tabular.needDocuments": "Select at least one document.",
  "tabular.needColumns": "Define at least one column with its question.",
  // Column types
  "coltype.text": "Text",
  "coltype.number": "Number",
  "coltype.percent": "Percentage",
  "coltype.monetary": "Monetary amount",
  "coltype.date": "Date",
  "coltype.yes_no": "Yes / No",
  "coltype.tag": "Tag (options)",
  // Tabular statuses
  "tabularStatus.draft": "Draft",
  "tabularStatus.running": "Running",
  "tabularStatus.complete": "Complete",
  "tabularStatus.failed": "Failed",
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
