from typing import List, Sequence

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


class MyFaiss(FAISS):
    def get_by_ids(self, ids: Sequence[str], /) -> List[Document]:
        return [
            self.docstore._dict[id]
            for id in (ids if isinstance(ids, list) else [ids])
            if id in self.docstore._dict
        ]  # type: ignore

    async def aget_by_ids(self, ids: Sequence[str], /) -> List[Document]:
        return self.get_by_ids(ids)

    def get_all_docs(self) -> dict[str, Document]:
        return self.docstore._dict  # type: ignore
