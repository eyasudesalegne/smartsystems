from .base import BaseConnectorAdapter, HttpConnectorAdapter, LocalArtifactAdapter, LocalOrHttpAdapter, ManualBridgeAdapter
from .antigravity_adapter import AntigravityAdapter
from .arxiv_adapter import ArxivAdapter
from .azure_ml_adapter import AzureMlAdapter
from .canvas_adapter import CanvasAdapter
from .drawio_adapter import DrawioAdapter
from .figma_adapter import FigmaAdapter
from .google_drive_adapter import GoogleDriveAdapter
from .kaggle_adapter import KaggleAdapter
from .mermaid_adapter import MermaidAdapter
from .mlflow_adapter import MlflowAdapter
from .notebooklm_adapter import NotebooklmAdapter
from .overleaf_adapter import OverleafAdapter
from .pubmed_adapter import PubmedAdapter
from .vscode_adapter import VscodeAdapter


def get_adapter(spec: dict[str, object]) -> BaseConnectorAdapter:
    mapping = {
        "mlflow": MlflowAdapter,
        "azure_ml": AzureMlAdapter,
        "drawio": DrawioAdapter,
        "figma": FigmaAdapter,
        "mermaid": MermaidAdapter,
        "canvas": CanvasAdapter,
        "kaggle": KaggleAdapter,
        "notebooklm": NotebooklmAdapter,
        "google_drive": GoogleDriveAdapter,
        "overleaf": OverleafAdapter,
        "pubmed": PubmedAdapter,
        "arxiv": ArxivAdapter,
        "antigravity": AntigravityAdapter,
        "vscode": VscodeAdapter,
    }
    cls = mapping.get(spec["service_name"], BaseConnectorAdapter)
    return cls(spec)
