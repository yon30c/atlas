"""CAM-gated execution for the initial read-only workspace capabilities."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.application.workspace_file_reading import WorkspaceFileReadingService
from atlas.application.workspace_listing import WorkspaceListingService
from atlas.assistant.capabilities import (
    CapabilityCatalog,
    CapabilityRisk,
    build_default_capability_catalog,
)
from atlas.assistant.planning import AssistantPlan, IntentKind
from atlas.assistant.workspace import WorkspaceFile, WorkspaceListing
from atlas.authorization.evaluator import AuthorizationEvaluator
from atlas.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
)
from atlas.core.context import OperationContext
from atlas.core.errors import AuthorizationError, ContractError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.memory.models import EnvironmentId, ProjectId


@dataclass(frozen=True, slots=True)
class WorkspaceCapabilityExecutionResult:
    """Resultado real de una capacidad workspace autorizada."""

    plan_id: str
    capability: IntentKind
    workspace_id: str
    resource_id: str
    grant_id: str
    grant_revision: int
    result: WorkspaceListing | WorkspaceFile

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id.strip():
            raise ContractError("plan_id debe ser texto no vacío")
        if not isinstance(self.capability, IntentKind):
            raise ContractError("capability debe ser IntentKind")
        for field in ("workspace_id", "resource_id", "grant_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{field} debe ser texto no vacío")
        if (
            isinstance(self.grant_revision, bool)
            or not isinstance(self.grant_revision, int)
            or self.grant_revision < 1
        ):
            raise ContractError("grant_revision debe ser un entero positivo")
        expected_type = (
            WorkspaceListing
            if self.capability is IntentKind.WORKSPACE_LIST
            else WorkspaceFile
        )
        if not isinstance(self.result, expected_type):
            raise ContractError("result no corresponde a la capacidad ejecutada")


class WorkspaceCapabilityExecutionService:
    """Ejecuta list/read con CAM y mantiene la UoW durante el acceso protegido.

    Política inicial: los workspaces de este perfil pertenecen al usuario
    canónico autenticado. El modelo no proporciona owner, proyecto ni entorno.
    La ejecución solo admite un paso READ_ONLY revisado explícitamente.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: SQLiteLocalAuthorityUnitOfWorkFactory,
        listing_service: WorkspaceListingService,
        reading_service: WorkspaceFileReadingService,
        catalog: CapabilityCatalog | None = None,
        evaluator: AuthorizationEvaluator | None = None,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        if not callable(getattr(listing_service, "list", None)):
            raise ContractError("listing_service debe implementar list")
        if not callable(getattr(reading_service, "read", None)):
            raise ContractError("reading_service debe implementar read")
        self._unit_of_work_factory = unit_of_work_factory
        self._listing_service = listing_service
        self._reading_service = reading_service
        self._catalog = catalog or build_default_capability_catalog()
        if not isinstance(self._catalog, CapabilityCatalog):
            raise ContractError("catalog debe ser CapabilityCatalog")
        self._evaluator = evaluator or AuthorizationEvaluator()

    @staticmethod
    def workspace_file_resource_id(workspace_id: str, path: str) -> str:
        """ID canónico, sin ambigüedad, para un archivo dentro de un workspace."""
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser texto no vacío")
        if not isinstance(path, str) or not path.strip():
            raise ContractError("path debe ser texto no vacío")
        return json.dumps(
            [workspace_id, path],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _validate_now(now: datetime) -> None:
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() != timedelta(0)
        ):
            raise ContractError("now debe ser un datetime UTC")

    def execute(
        self,
        plan: AssistantPlan,
        context: OperationContext,
        now: datetime,
        *,
        review_confirmed: bool,
    ) -> WorkspaceCapabilityExecutionResult:
        """Autoriza y ejecuta un único paso de lectura dentro de la UoW CAM."""
        if not isinstance(plan, AssistantPlan):
            raise ContractError("plan debe ser AssistantPlan")
        if not isinstance(context, OperationContext):
            raise ContractError("context debe ser OperationContext")
        self._validate_now(now)
        if not isinstance(review_confirmed, bool):
            raise ContractError("review_confirmed debe ser bool")
        if review_confirmed is not True:
            raise AuthorizationError("el plan requiere confirmación explícita")

        actor = context.actor
        if (
            actor.kind is not IdentityKind.USER
            or actor.status is not IdentityStatus.ACTIVE
            or context.delegation is not None
        ):
            raise AuthorizationError("se requiere una identidad USER activa y directa")
        if not context.project_id or not context.environment:
            raise AuthorizationError("proyecto y entorno deben resolverse de forma confiable")

        definition = self._catalog.validate_intent(plan.intent)
        if definition.risk is not CapabilityRisk.READ_ONLY:
            raise AuthorizationError("el perfil solo admite capacidades READ_ONLY")
        if len(plan.steps) != 1:
            raise ContractError("el perfil inicial exige exactamente un paso")
        step = plan.steps[0]
        if (
            step.capability is not plan.intent.kind
            or dict(step.parameters) != dict(plan.intent.parameters)
        ):
            raise ContractError("el paso no coincide exactamente con la intención revisada")

        parameters = dict(plan.intent.parameters)
        workspace_id = parameters["workspace_id"]
        if plan.intent.kind is IntentKind.WORKSPACE_LIST:
            action = IntentKind.WORKSPACE_LIST.value
            resource_type = "workspace"
            resource_id = workspace_id
        elif plan.intent.kind is IntentKind.WORKSPACE_READ:
            path = parameters["path"]
            action = IntentKind.WORKSPACE_READ.value
            resource_type = "workspace_file"
            resource_id = self.workspace_file_resource_id(workspace_id, path)
        else:
            raise AuthorizationError("capacidad no admitida")

        # The UoW uses BEGIN IMMEDIATE. Identity, Grant, Project and Environment
        # are read from the same transaction, and remain fenced from SQLite
        # writers while the protected filesystem read/list is performed.
        with self._unit_of_work_factory() as unit:
            canonical = unit.identity.get_user(context.user_id)
            if (
                canonical is None
                or canonical.user_id != context.user_id
                or canonical.identity != actor
            ):
                raise AuthorizationError("la identidad canónica no coincide con el contexto")

            project = unit.project_environments.get_project(ProjectId(context.project_id))
            environment = unit.project_environments.get_environment(
                EnvironmentId(context.environment)
            )
            if project is None or project.status != "active":
                raise AuthorizationError("el proyecto no existe o no está activo")
            if environment is None or environment.status != "active":
                raise AuthorizationError("el entorno no existe o no está activo")

            request = AuthorizationRequest(
                context=context,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_owner_id=canonical.user_id,
            )
            grants = unit.grants.list_by_owner(canonical.user_id)
            evaluation = self._evaluator.evaluate(request, grants, now)
            if (
                evaluation.decision is not AuthorizationDecision.ALLOW
                or evaluation.matched_grant is None
            ):
                raise AuthorizationError("CAM no autorizó el recurso y la acción exactos")

            grant = evaluation.matched_grant
            if plan.intent.kind is IntentKind.WORKSPACE_LIST:
                result = self._listing_service.list(workspace_id)
            else:
                result = self._reading_service.read(workspace_id, parameters["path"])

            return WorkspaceCapabilityExecutionResult(
                plan_id=plan.plan_id,
                capability=plan.intent.kind,
                workspace_id=workspace_id,
                resource_id=resource_id,
                grant_id=grant.grant_id,
                grant_revision=grant.revision,
                result=result,
            )
