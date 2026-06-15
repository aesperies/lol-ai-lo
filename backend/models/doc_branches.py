"""Specialized drafting-agent branches (drafting-agents feature).

Each catalog branch (DOC_TYPE_CATALOG in models/schema.py) maps to a
:class:`Branch` with a focused drafting **persona + checklist**
(:data:`BRANCH_GUIDANCE`). The persona is passed to the LLM as the ``system``
message by services/drafting_agents.py; it never edits the verbatim
``GENERATION_PROMPT``. Uncatalogued / "Otros" doc_types fall back to
:attr:`Branch.GENERIC`.

The guidance instructs the model only — it is bilingual-agnostic. Output
language always follows the request (the GENERATION_PROMPT carries {language}).
"""
from __future__ import annotations

from enum import Enum

from models.schema import DOC_TYPE_CATALOG


class Branch(str, Enum):
    """The specialized drafting branches, one per catalog group (+ generic)."""

    GOBIERNO_CORPORATIVO = "gobierno_corporativo"
    OPERACIONES_DE_FONDO = "operaciones_de_fondo"
    GESTION_DE_PORTFOLIO = "gestion_de_portfolio"
    CUMPLIMIENTO_REGULATORIO = "cumplimiento_regulatorio"
    CONTRATOS_TERCEROS = "contratos_terceros"
    GENERIC = "generic"


# Catalog group label (DOC_TYPE_CATALOG key) -> Branch. The labels carry the
# SPEC emoji prefix, so we match on the stable substring instead of the full
# key to stay robust to emoji/whitespace drift.
_GROUP_LABEL_TO_BRANCH: dict[str, Branch] = {
    "Gobierno Corporativo": Branch.GOBIERNO_CORPORATIVO,
    "Operaciones de Fondo": Branch.OPERACIONES_DE_FONDO,
    "Gestión de Portfolio": Branch.GESTION_DE_PORTFOLIO,
    "Cumplimiento y Regulatorio": Branch.CUMPLIMIENTO_REGULATORIO,
    "Contratos con Terceros": Branch.CONTRATOS_TERCEROS,
}


def _build_doc_type_index() -> dict[str, Branch]:
    """Map every catalog doc_type label to its Branch (derived from the
    grouped catalog, so it cannot drift out of sync with the SPEC)."""
    index: dict[str, Branch] = {}
    for group_label, doc_types in DOC_TYPE_CATALOG.items():
        branch = Branch.GENERIC
        for needle, candidate in _GROUP_LABEL_TO_BRANCH.items():
            if needle in group_label:
                branch = candidate
                break
        for doc_type in doc_types:
            index[doc_type] = branch
    return index


_DOC_TYPE_TO_BRANCH = _build_doc_type_index()


def branch_for(doc_type: str) -> Branch:
    """Resolve a request's doc_type to its drafting :class:`Branch`.

    Exact catalog matches win; anything uncatalogued (including the "Other:
    ..." effective doc_type produced for free-form requests and the catalog's
    "Otros" group) maps to :attr:`Branch.GENERIC`.
    """
    return _DOC_TYPE_TO_BRANCH.get(doc_type, Branch.GENERIC)


# ---------------------------------------------------------------------------
# Per-branch drafting personas + checklists (the system message)
# ---------------------------------------------------------------------------

BRANCH_GUIDANCE: dict[Branch, str] = {
    Branch.GOBIERNO_CORPORATIVO: (
        "You are a senior corporate-governance counsel for European VC fund "
        "management companies, expert in actas, resoluciones and powers of "
        "attorney. Drafting checklist:\n"
        "- Use the correct instrument structure: encabezamiento, orden del día, "
        "deliberaciones, acuerdos, cierre and signatures.\n"
        "- State the convening basis, quórum de constitución and quórum de "
        "votación; record the majority by which each acuerdo passed.\n"
        "- Identify the órgano (consejo / junta general), its members and their "
        "capacities; for per rollam / sin reunión, evidence the written-consent "
        "basis.\n"
        "- For powers of attorney, scope the facultades precisely and flag any "
        "limits, joint/several signing and revocation terms.\n"
        "- Keep dates, place and signatory blocks consistent throughout."
    ),
    Branch.OPERACIONES_DE_FONDO: (
        "You are a senior fund-operations counsel expert in capital-call and "
        "distribution mechanics and the limited partnership agreement (LPA). "
        "Drafting checklist:\n"
        "- Anchor every notice to the governing LPA clause (drawdown / "
        "distribution / extension provisions) and to the relevant defined "
        "terms (Commitment, Drawn/Undrawn, Distributable Proceeds).\n"
        "- For capital calls: state amount called, per-investor allocation "
        "basis, due date, payment account and default consequences.\n"
        "- For distributions: state the distribution waterfall step, amounts, "
        "tax/withholding treatment and record date.\n"
        "- For period/term extensions: cite the LPA extension right, required "
        "consents (GP / advisory committee / LP majority) and the new dates.\n"
        "- Keep currency, amounts and pro-rata maths internally consistent."
    ),
    Branch.GESTION_DE_PORTFOLIO: (
        "You are a senior VC investment counsel expert in term sheets, SPAs and "
        "portfolio transaction documents. Drafting checklist:\n"
        "- Follow standard term-sheet / SPA structure and mark non-binding "
        "instruments clearly (binding-only carve-outs: confidentiality, "
        "exclusivity, governing law, costs).\n"
        "- Cover the economic core: valuation/price, instrument, ownership %, "
        "option pool, liquidation preference, anti-dilution.\n"
        "- Cover control/governance: board, protective provisions, information "
        "rights, pro-rata, drag/tag, ROFR.\n"
        "- For NDAs/LOIs: scope confidential information, term, permitted use "
        "and carve-outs.\n"
        "- Keep conditions precedent, reps & warranties and closing mechanics "
        "consistent with the agreed terms."
    ),
    Branch.CUMPLIMIENTO_REGULATORIO: (
        "You are a senior regulatory & compliance counsel for European VC fund "
        "managers, fluent in AIFMD, CNMV/AMF/BaFin practice and AML/KYC "
        "requirements. Drafting checklist:\n"
        "- Use precise regulatory phrasing and cite the applicable regime "
        "(AIFMD article / national transposition, AML/KYC obligations) where "
        "the instrument requires it.\n"
        "- For UBO / AML / KYC: identify the obligated entity, the verification "
        "basis and the declarant's capacity; include required statements of "
        "truthfulness.\n"
        "- For regulator communications / AIFMD notifications: address the "
        "correct authority, reference the relevant filing and state the "
        "regulatory deadline.\n"
        "- Include the appropriate disclaimers and data-protection notices; do "
        "not assert regulatory conclusions not supported by the inputs.\n"
        "- Keep tax-residence / certification language jurisdiction-correct."
    ),
    Branch.CONTRATOS_TERCEROS: (
        "You are a senior commercial counsel expert in services, advisory and "
        "delegated-management agreements and investor side letters. Drafting "
        "checklist:\n"
        "- Define scope of services / advisory mandate, deliverables and "
        "service levels precisely.\n"
        "- Set fees/remuneration, payment terms, expenses and any "
        "success/retainer split clearly.\n"
        "- Cover term, termination (for cause / convenience), and survival.\n"
        "- Allocate liability, indemnities, confidentiality, IP ownership and "
        "data protection; flag conflicts-of-interest handling.\n"
        "- For side letters: tie each provision to the underlying LPA clause it "
        "varies and confirm MFN consistency.\n"
        "- Keep governing law, jurisdiction and notices coherent."
    ),
    Branch.GENERIC: (
        "You are a senior European VC fund legal document drafter handling an "
        "uncatalogued document type. Drafting checklist:\n"
        "- Infer the appropriate structure for this instrument and follow it "
        "consistently (heading, recitals/parties, operative clauses, "
        "signatures).\n"
        "- Apply formal legal register appropriate to the stated jurisdiction "
        "and 2026 European VC market standards.\n"
        "- Cover the parties, key economic and governance terms supplied, and "
        "the governing law / jurisdiction.\n"
        "- Do not invent parties, amounts or dates; flag gaps explicitly."
    ),
}


def guidance_for(branch: Branch) -> str:
    """The persona + checklist system message for a branch (GENERIC fallback)."""
    return BRANCH_GUIDANCE.get(branch, BRANCH_GUIDANCE[Branch.GENERIC])
