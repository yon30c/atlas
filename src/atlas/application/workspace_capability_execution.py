"""CAM-gated execution for canonical, registry-backed read-only workspaces."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path

from atlas.adapters.local_workspace import LocalWorkspaceAdapter
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
from atlas.ports.workspace_mounts import WorkspaceMountResolver
from atlas.workspace.models import (
    ProjectEnvironmentStatus,
    WorkspaceStatus,
)


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
    """Ejecuta list/read desde el registro canónico y bajo CAM.

    El resolver de mounts debe proceder de composición confiable. El caller
    solo aporta workspace_id y, para lectura, una ruta relativa dentro de él.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: SQLiteLocalAuthorityUnitOfWorkFactory,
        mount_resolver: WorkspaceMountResolver,
        catalog: CapabilityCatalog | None = None,
        evaluator: AuthorizationEvaluator | None = None,
    ) -> None:
        if not callable(unit_of_work_factory):
            raise ContractError("unit_of_work_factory debe ser invocable")
        if not callable(getattr(mount_resolver, "resolve", None)):
            raise ContractError("mount_resolver debe implementar resolve(root_ref)")
        self._unit_of_work_factory = unit_of_work_factory
        self._mount_resolver = mount_resolver
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
        """Revalida autoridad y Grant antes de resolver el mount y tocar disco."""
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

        # BEGIN IMMEDIATE fences canonical SQLite writers through the filesystem
        # read. This is not a filesystem lock or a distributed consistency gate.
        with self._unit_of_work_factory() as unit:
            canonical = unit.identity.get_user(context.user_id)
            if (
                canonical is None
                or canonical.user_id != context.user_id
                or canonical.identity != actor
            ):
                raise AuthorizationError("la identidad canónica no coincide con el contexto")

            workspace = unit.workspaces.get_workspace(workspace_id)
            if workspace is None or workspace.status is not WorkspaceStatus.ACTIVE:
                raise AuthorizationError("el workspace no existe o no está activo")
            if workspace.owner_user_id != canonical.user_id:
                raise AuthorizationError("el workspace no pertenece al usuario canónico")
            if (
                str(workspace.project_id) != context.project_id
                or str(workspace.environment_id) != context.environment
            ):
                raise AuthorizationError("el workspace no coincide con el ámbito del contexto")

            project = unit.project_environments.get_project(workspace.project_id)
            environment = unit.project_environments.get_environment(
                workspace.environment_id
            )
            if project is None or project.status != "active":
                raise AuthorizationError("el proyecto no existe o no está activo")
            if environment is None or environment.status != "active":
                raise AuthorizationError("el entorno no existe o no está activo")

            association = unit.project_environment_associations.get_association(
                workspace.project_id, workspace.environment_id
            )
            if (
                association is None
                or association.status is not ProjectEnvironmentStatus.ACTIVE
            ):
                raise AuthorizationError("la asociación Project/Environment no está activa")

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

            # Resolve only registry-controlled root_ref after exact CAM ALLOW.
            try:
                root = self._mount_resolver.resolve(workspace.root_ref)
            except (ContractError, OSError, ValueError) as exc:
                raise AuthorizationError("el mount confiable no está disponible") from exc
            if not isinstance(root, (str, Path)):
                raise AuthorizationError("el resolver devolvió una raíz inválida")

            adapter = LocalWorkspaceAdapter({workspace.workspace_id: root})
            listing_service = WorkspaceListingService(adapter)
            reading_service = WorkspaceFileReadingService(adapter)
            if plan.intent.kind is IntentKind.WORKSPACE_LIST:
                result = listing_service.list(workspace.workspace_id)
            else:
                result = reading_service.read(
                    workspace.workspace_id, parameters["path"]
                )

            grant = evaluation.matched_grant
            return WorkspaceCapabilityExecutionResult(
                plan_id=plan.plan_id,
                capability=plan.intent.kind,
                workspace_id=workspace.workspace_id,
                resource_id=resource_id,
                grant_id=grant.grant_id,
                grant_revision=grant.revision,
                result=result,
            )
