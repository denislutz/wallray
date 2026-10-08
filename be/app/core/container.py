from dataclasses import dataclass

from app.adapters.email.resend import ResendAdapter
from app.adapters.renderer.xhtml2pdf import Xhtml2pdfAdapter
from app.adapters.storage.s3 import S3StorageAdapter
from app.adapters.vision_llm.anthropic import AnthropicAdapter
from app.adapters.vision_llm.fake import FakeVisionLLMAdapter
from app.core.config import settings
from app.domain.ports.vision_llm import VisionLLMPort


@dataclass
class Container:
    storage: S3StorageAdapter
    vision_llm: VisionLLMPort
    fake_vision_llm: VisionLLMPort
    renderer: Xhtml2pdfAdapter
    email: ResendAdapter


def build() -> Container:
    storage = S3StorageAdapter(
        bucket=settings.storage_bucket,
        endpoint_url=settings.storage_endpoint_url or None,
        access_key=settings.storage_access_key_id,
        secret_key=settings.storage_secret_access_key,
        region=settings.storage_region,
    )
    return Container(
        storage=storage,
        vision_llm=AnthropicAdapter(
            api_key=settings.anthropic_api_key,
            storage=storage,
            classification_model=settings.anthropic_classification_model,
            assessment_model=settings.anthropic_assessment_model,
        ),
        fake_vision_llm=FakeVisionLLMAdapter(),
        renderer=Xhtml2pdfAdapter(),
        email=ResendAdapter(
            api_key=settings.resend_api_key,
            from_address=settings.resend_from_address,
        ),
    )
