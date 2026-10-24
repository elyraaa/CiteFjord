"""Retrieval keeps short PDF lists together across consecutive slides."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.retriever import Source, ask, search_index


class FakeStore:
    def similarity_search_with_score(self, _query, *, k):
        def document(text, page):
            return SimpleNamespace(
                page_content=text,
                metadata={
                    "source": r"C:\docs\family.pdf",
                    "source_root": r"C:\docs",
                    "file_name": "family.pdf",
                    "page": page,
                },
            )

        return [
            (document("The Family\nLucia\nMaria", 11), 0.2),
            (document("An unrelated passage", 40), 0.35),
        ][:k]

    def get(self, *, where, include):
        assert where == {"source": r"C:\docs\family.pdf"}
        assert include == ["documents", "metadatas"]
        return {
            "documents": ["The Family\nSaturnina\nPaciano", "The Family\nTrinidad\nSoledad"],
            "metadatas": [{"page": 10}, {"page": 12}],
        }


class NeighborRetrievalTests(unittest.TestCase):
    def test_short_continuing_pdf_list_adds_adjacent_pages(self):
        sources, _ = search_index(FakeStore(), "Who are the siblings?", k=4)
        self.assertEqual([source.page for source in sources], [11, 12, 13, 41])
        self.assertEqual([source.number for source in sources], [1, 2, 3, 4])
        self.assertIn("Saturnina", sources[0].content)
        self.assertIn("Soledad", sources[2].content)

    def test_nearby_pages_take_priority_over_distant_shared_heading(self):
        class WiderStore(FakeStore):
            def similarity_search_with_score(self, _query, *, k):
                document = SimpleNamespace(
                    page_content="Political Development\nThe opening of a canal",
                    metadata={"source": r"C:\docs\family.pdf", "source_root": r"C:\docs", "file_name": "family.pdf", "page": 13},
                )
                return [(document, 0.2)]

            def get(self, *, where, include):
                return {
                    "documents": [f"Political Development\nPage {page}" for page in (12, 13, 14, 15, 16)],
                    "metadatas": [{"page": page - 1} for page in (12, 13, 14, 15, 16)],
                }

        sources, _ = search_index(WiderStore(), "What followed the canal opening?", k=4)
        self.assertEqual([source.page for source in sources], [13, 14, 15, 16])

    def test_name_list_stops_before_prose_under_same_heading(self):
        class ListStore(FakeStore):
            def similarity_search_with_score(self, _query, *, k):
                document = SimpleNamespace(
                    page_content="The Family\nALICE\nBOB\nCAROL",
                    metadata={"source": r"C:\docs\family.pdf", "source_root": r"C:\docs", "file_name": "family.pdf", "page": 11},
                )
                return [(document, 0.2)]

            def get(self, *, where, include):
                return {
                    "documents": ["The Family\nDAN\nERIN", "The Family\nThe family lived in a large house."],
                    "metadatas": [{"page": 12}, {"page": 13}],
                }

        sources, _ = search_index(ListStore(), "Who are the children?", k=4)
        self.assertEqual([source.page for source in sources], [12, 13])

    def test_list_questions_retrieve_more_context_without_topic_rules(self):
        source = Source(1, "notes.pdf", "notes.pdf", "notes.pdf", 1, 0.2, "Names on the list")
        with patch("src.retriever.retrieve", return_value=((source,), 0.01)) as retrieve, \
             patch("src.retriever._generate", return_value="Answer [1]"):
            self.assertEqual(ask("Who are the members?").answer, "Answer [1]")
            self.assertEqual(retrieve.call_args.kwargs["k"], 8)
            ask("When was it founded?")
            self.assertEqual(retrieve.call_args.kwargs["k"], 4)


if __name__ == "__main__":
    unittest.main()
