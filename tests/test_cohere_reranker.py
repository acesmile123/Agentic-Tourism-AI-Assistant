from types import SimpleNamespace

from langchain_core.documents import Document

from tourism_agent.services.reranking import CohereReranker


class FakeCohereClient:
    def rerank(self, **kwargs):
        assert kwargs["model"] == "rerank-v4.0-pro"
        assert kwargs["top_n"] == 2
        return SimpleNamespace(results=[
            SimpleNamespace(index=1, relevance_score=0.9),
            SimpleNamespace(index=0, relevance_score=0.7),
        ])


class FailingCohereClient:
    def rerank(self, **kwargs):
        raise TimeoutError("timeout")


def test_cohere_reranker_maps_result_indices_back_to_documents():
    docs = [Document(page_content="A"), Document(page_content="B")]
    reranker = CohereReranker("", client=FakeCohereClient())

    result = reranker.rerank("query", docs, top_n=2)

    assert [document.page_content for document in result] == ["B", "A"]
    assert result[0].metadata["_rerank_score"] == 0.9


def test_cohere_reranker_falls_back_to_rrf_order():
    docs = [Document(page_content="A"), Document(page_content="B")]
    reranker = CohereReranker("", client=FailingCohereClient())

    result = reranker.rerank("query", docs, top_n=1)

    assert result == docs[:1]
