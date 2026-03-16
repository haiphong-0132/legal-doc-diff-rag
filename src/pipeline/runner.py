import sys
import os
import subprocess
from pathlib import Path
import json
from tqdm import tqdm
from tkinter import Tk, filedialog

def select_file():
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.update()

    file_path = filedialog.askopenfilename(
        title='Chọn file',
        filetypes=[
            ('Documents', '*.pdf *.docx'),
            ('PDF', '*.pdf'),
            ('Word', '*.docx'),
            ('All files', '*.*')
        ]
    )
    root.destroy()
    return file_path if file_path else None

def process_document(
    file_path: str,
    **kwargs
):
    """
    Pipeline chính để xử lý tài liệu từ file -> text -> chunk -> embedding.

    Args:
        file_path: Đường dẫn file pdf/docx
        **kwargs: Tham số riêng của chunking strategy, embedding model và vector database
               
                 chunker_params: {
                    strategy: 'fixed_size'
                    ... các tham số tùy strategy
                }
                embedding_params: {
                    model_dir: str (đường dẫn đến thư mục chứa model ONNX và tokenizer)
                    ... các tham số tùy mô hình
                }
                store_params: {
                    collection_name: str,
                    is_persist: bool,
                    distance_metric: str
                    ...
                }
    
    Returns:
        dict: {
            'success': True/False, 
            'message': '...',
            'collection': collection_name (nếu success)
        }
    """
    from src.core.ingestion.extractor import extract_file
    from src.core.chunker.factory import create_chunker
    from src.core.chunker.hierarchical import build_json_tree
    from src.core.embedding.embedding import EmbeddingPipeline
    from src.core.embedding.onnx_embedding import OnnxEmbeddingModel
    from src.core.vector_store.chroma_store import ChromaStore
    from src.core.vector_store.vectorstore import VectorStorePipeline
    from src.schemas import ChromaConfig
    
    try:
        # 1. Ingestion
        tqdm.write(f'Start process document: {file_path}')
        tqdm.write('Extracting text from document')
        if not file_path:
            raise ValueError("No file selected. Please select a file to process.")
        if os.path.exists(file_path):
            text = extract_file(file_path)
        else:            
            raise FileNotFoundError(f"File not found: {file_path}")

        # 2. Chunking
        chunker_params = kwargs.get('chunker_params', {}).copy()
        chunking_strategy = chunker_params.pop('strategy', 'fixed_size')

        tqdm.write(f'Chunking with strategy: {chunking_strategy}')
        chunker = create_chunker(
            strategy=chunking_strategy,
            **chunker_params
        )

        if chunking_strategy == 'hierarchical':
            text = build_json_tree(text)  # Chuyển raw text thành cấu trúc JSON nếu dùng hierarchical chunker

        chunks = chunker.chunk(text)
        tqdm.write(f'Generated {len(chunks)} chunks')

        # 3. Embedding
        tqdm.write('Generating embeddings')
        embedding_model = OnnxEmbeddingModel(
            **kwargs.get('embedding_params', {})
        )

        embedding_pipeline = EmbeddingPipeline(chunk_documents=chunks)
        embeddings = embedding_pipeline.run(embedding_model.embed)
        
        tqdm.write(f'Generated {len(embeddings)} embeddings')

        # 4. Vector Store
        chroma_store = ChromaStore(
            ChromaConfig(**kwargs.get('store_params', {}))
        )
        vector_store_pipeline = VectorStorePipeline(
            chunks=chunks,
            embeddings=embeddings
        )
        vector_store_pipeline.run(chroma_store)
        tqdm.write(f'Upserted chunks into vector store: {chroma_store.config.collection_name}')

        # Test showing all documents in collection
        # Uncomment block này để test nội dung collection sau khi upsert
        results = chroma_store.collection.get(include=['documents', 'metadatas'])
        with open('debug_chroma_collection.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        tqdm.write('Chroma collection content saved to debug_chroma_collection.json')
        
        tqdm.write('Finish processing document (input -> ... -> store)')


    except Exception as e:
        tqdm.write(f"Error processing document: {e}")

if __name__ == "__main__":
    process_document(
        file_path=select_file(),
        chunker_params={
            'strategy': 'hierarchical',
        },
        embedding_params={
            'model_dir': './models/Vietnamese_Embedding_v2',
        },
        store_params={
            'collection_name': 'test_collection',
            'is_persist': True,
            'persist_directory': './chroma_db',
            'distance_metric': 'ip'
        }

    )
    
