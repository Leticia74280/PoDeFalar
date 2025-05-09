import pdfplumber
import os

caminho_pdf = "PDFs/teste.pdf"
nome_arquivo = os.path.splitext(os.path.basename(caminho_pdf))[0]

os.makedirs("TextoExtraido", exist_ok=True)

contador = 1
caminho_saida = f"TextoExtraido/{nome_arquivo}.txt"
while os.path.exists(caminho_saida):
    caminho_saida = f"TextoExtraido/{nome_arquivo}_{contador}.txt"
    contador += 1

with pdfplumber.open(caminho_pdf) as pdf:
    texto = ""
    for pagina in pdf.pages:
        pagina_texto = pagina.extract_text()
        if pagina_texto:
            texto += pagina_texto + "\n"

with open(caminho_saida, "w", encoding="utf-8") as arquivo:
    arquivo.write(texto)

print(f"Texto salvo em: {caminho_saida}")
