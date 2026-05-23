import logging

import chromadb
from chromadb.utils import embedding_functions

# Configure logger
logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    Manages the Vector Store (ChromaDB) for Dynamic Few-Shot RAG.

    Uses 'all-MiniLM-L6-v2' for efficient local embeddings.
    """

    def __init__(
        self, collection_name: str = "sql_examples", persist_directory: str = "./chroma_db"
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.client = None
        self.collection = None
        self.embedding_function = None

        # Initialize immediately
        self._initialize()

    def _initialize(self):
        """Initialize ChromaDB client and collection"""
        try:
            logger.info(f"Initializing VectorStoreManager (Collection: {self.collection_name})")

            # Use persistent client
            self.client = chromadb.PersistentClient(path=self.persist_directory)

            # Initialize embedding function (using sentence-transformers)
            # This runs locally on CPU
            # Using multilingual model for better Portuguese support
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="paraphrase-multilingual-MiniLM-L12-v2"
            )

            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name, embedding_function=self.embedding_function
            )

            logger.info("VectorStoreManager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize VectorStoreManager: {e}")
            raise

    def add_examples(self, examples: list[dict[str, str]]):
        """
        Add examples to the vector store.

        Args:
            examples: List of dicts with 'question' and 'sql' keys.
        """
        try:
            if not examples:
                return

            ids = []
            documents = []
            metadatas = []

            for i, ex in enumerate(examples):
                # Create a unique ID based on hash or index
                ex_id = f"ex_{hash(ex['question']) % 100000}_{i}"

                ids.append(ex_id)
                documents.append(ex["question"])
                metadatas.append({"sql": ex["sql"]})

            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)

            logger.info(f"Added {len(examples)} examples to vector store")

        except Exception as e:
            logger.error(f"Failed to add examples: {e}")
            raise

    def search_examples(self, query: str, k: int = 3) -> list[dict[str, str]]:
        """
        Search for similar examples.

        Args:
            query: User question.
            k: Number of results to return.

        Returns:
            List of dicts with 'question' and 'sql'.
        """
        try:
            results = self.collection.query(query_texts=[query], n_results=k)

            examples = []
            if results["ids"]:
                # Chroma returns list of lists (one per query)
                for i in range(len(results["ids"][0])):
                    examples.append(
                        {
                            "question": results["documents"][0][i],
                            "sql": results["metadatas"][0][i]["sql"],
                        }
                    )

            return examples

        except Exception as e:
            logger.error(f"Failed to search examples: {e}")
            return []

    def count(self) -> int:
        """Return total number of examples"""
        return self.collection.count()
