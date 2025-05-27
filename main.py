import streamlit as st
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from tabulate import tabulate
import chromadb
from sentence_transformers import SentenceTransformer
import ollama

# NOME DO CHATBOT E FERRAMENTA DE UPLOAD
st.write("# Chat PoDeFalar")
uploaded_file = st.file_uploader("Escolha um arquivo PDF", type="pdf")

if uploaded_file is not None:
    # SALVA O PDF TEMPORARIAMENTE
    with open("temp_pdf_file.pdf", "wb") as temp_file:
        temp_file.write(uploaded_file.read())

    # CONFIGS DA API DA AZURE
    AZURE_COGNITIVE_ENDPOINT = "https://chatpdf-analyzer.cognitiveservices.azure.com"
    AZURE_API_KEY = "EIPhBhw87dYoHWzdFdo7SxePB4476fbDkbQD2GMsW0QwfScZTeiEJQQJ99BEACZoyfiXJ3w3AAAEACOGvmXU"
    credential = AzureKeyCredential(AZURE_API_KEY)
    AZURE_DOCUMENT_ANALYSIS_CLIENT = DocumentAnalysisClient(AZURE_COGNITIVE_ENDPOINT, credential)

    # ENVIA PRA OCR
    with open("temp_pdf_file.pdf", "rb") as f:
        poller = AZURE_DOCUMENT_ANALYSIS_CLIENT.begin_analyze_document("prebuilt-document", document=f)
        doc_info = poller.result().to_dict()

    # PROCESSA O RESULTADO
    res = []
    CONTENT = "content"
    PAGE_NUMBER = "page_number"
    TYPE = "type"
    RAW_CONTENT = "raw_content"
    TABLE_CONTENT = "table_content"

    for p in doc_info['pages']:
        item = {}
        page_content = " ".join([line["content"] for line in p["lines"]])
        item[CONTENT] = str(page_content)
        item[PAGE_NUMBER] = str(p["page_number"])
        item[TYPE] = RAW_CONTENT
        res.append(item)

    for table in doc_info["tables"]:
        item = {}
        item[PAGE_NUMBER] = str(table["bounding_regions"][0]["page_number"])
        col_headers = []
        cells = table["cells"]

        for cell in cells:
            if cell["kind"] == "columnHeader" and cell["column_span"] == 1:
                for _ in range(cell["column_span"]):
                    col_headers.append(cell["content"])

        data_rows = [[] for _ in range(table["row_count"])]
        for cell in cells:
            if cell["kind"] == "content":
                for _ in range(cell["column_span"]):
                    data_rows[cell["row_index"]].append(cell["content"])
        data_rows = [row for row in data_rows if len(row) > 0]

        markdown_table = tabulate(data_rows, headers=col_headers, tablefmt="pipe")
        item[CONTENT] = markdown_table
        item[TYPE] = TABLE_CONTENT
        res.append(item)

    # EXIBE O CONTEUDO QUE ELE EXTRAIU
    st.subheader("Conteúdo formatado (texto e tabelas)")
    for item in res:
        st.markdown(f"### Página {item[PAGE_NUMBER]}")
        if item[TYPE] == RAW_CONTENT:
            st.write(item[CONTENT])
        elif item[TYPE] == TABLE_CONTENT:
            st.markdown(item[CONTENT])

    # EMBEDDING LOCAL COM SENTENCE-TRANSFORMERS
    model = SentenceTransformer("all-MiniLM-L6-v2")

    class LocalEmbeddingFunction:
        def __call__(self, input: list[str]):
            return model.encode(input).tolist()

    # CRIA CLIENTE DO CHROMADB E COLEÇÃO
    client = chromadb.Client()
    embedding_fn = LocalEmbeddingFunction()

    try:
        collection = client.get_or_create_collection(name="my_collection", embedding_function=embedding_fn)
    except Exception as e:
        st.error(f"Erro ao criar ou carregar a coleção: {e}")
        collection = None

    id = 1
    for item in res:
        content = item.get(CONTENT, "")
        page_number = item.get(PAGE_NUMBER, "")
        type_of_content = item.get(TYPE, "")

        content_metadata = {
            PAGE_NUMBER: page_number,
            TYPE: type_of_content
        }

        if collection:
            collection.add(
                documents=[content],
                metadatas=[content_metadata],
                ids=[str(id)]
            )
            id += 1

    st.success("📚 Conteúdo armazenado com sucesso no ChromaDB!")

# ESTADO DO CHAT
if "messages" not in st.session_state:
    st.session_state.messages = []

# HISTÓRICO
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ENTRADA DO USUÁRIO
if prompt := st.chat_input("O que você quer perguntar ao seu PDF?"):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # RECUPERA TRECHOS RELEVANTES DO CHROMA DB
    q = collection.query(query_texts=[prompt], n_results=5)
    results = q["documents"][0]

    # MONTA O PROMPT PARA OLLAMA
    prompts = []
    for r in results:
        prompt_text = f"Responda com base apenas neste trecho:\n\n{r}\n\nPergunta: {prompt}"
        prompts.append(prompt_text)

    ollama_prompt = "\n\n".join(prompts)

    # GERA RESPOSTA COM OLLAMA
    try:
        ollama_response = ollama.chat(
            model="llama3",  # ou "mistral", "gemma", etc., dependendo do que você instalou
            messages=[
                {"role": "system", "content": "Você é um assistente que responde com base apenas no conteúdo fornecido."},
                {"role": "user", "content": ollama_prompt}
            ]
        )
        response = ollama_response["message"]["content"]
    except Exception as e:
        st.error(f"Erro ao gerar resposta com Ollama: {e}")
        response = "Não foi possível gerar uma resposta."

    # MOSTRA A RESPOSTA NO CHAT
    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
