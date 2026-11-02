#!/usr/bin/env python3
"""Divisor de O.S. - equipe noturna. Rode: python app.py  (abre em http://localhost:8000)
Só usa a biblioteca padrão do Python (nada para instalar)."""
import csv, io, json, os, webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_HIST = os.path.join(PASTA, "historico.json")
PORTA = 8000


def carregar():
    try:
        with open(ARQ_HIST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"nomes": [], "divisoes": {}}


def salvar(h):
    with open(ARQ_HIST, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)


def ler_csv(dados: bytes):
    """Lê o CSV (utf-8 ou cp1252, separador ;) e agrupa as linhas por Nr. O.S."""
    try:
        txt = dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = dados.decode("cp1252")
    delim = ";" if txt.split("\n", 1)[0].count(";") >= txt.split("\n", 1)[0].count(",") else ","
    grupos = {}
    for r in csv.DictReader(io.StringIO(txt), delimiter=delim):
        nr = (r.get("Nr. O.S.") or "").strip()
        if not nr:
            continue
        g = grupos.setdefault(nr, {
            "os": nr, "veiculo": (r.get("Veículo") or "").strip(),
            "garagem": (r.get("Garagem") or "").strip(),
            "data": (r.get("Data") or "").strip(),
            "origem": (r.get("Origem") or "").strip(), "itens": []})
        compl = (r.get("Complemento") or "").strip()
        g["itens"].append({
            "sistema": (r.get("Sistema") or "").strip(),
            "componente": (r.get("Componente") or "").strip(),
            "defeito": (r.get("Defeito") or "").strip(),
            "compl": compl[:160]})
    lista = list(grupos.values())
    for g in lista:
        try:
            g["_ts"] = datetime.strptime(g["data"], "%d/%m/%Y %H:%M").timestamp()
        except ValueError:
            g["_ts"] = 0
    return lista


def marcar_repetidas(lista, hist):
    """Uma O.S. que já foi dividida em noite anterior e continua no arquivo = não foi feita."""
    hoje = date.today().isoformat()
    anteriores = sorted(d for d in hist["divisoes"] if d < hoje)
    for g in lista:
        vezes, ult = 0, None
        for d in anteriores:
            a = hist["divisoes"][d]["atribuicoes"].get(g["os"])
            if a:
                vezes += 1
                ult = (d, a["pessoa"])
        g["repetida"] = vezes > 0
        g["vezes"] = vezes
        g["anterior"] = {"data": ult[0], "pessoa": ult[1]} if ult else None
    return lista


def dividir(lista, nomes, motivos, hist):
    """Prioridade (repetidas) primeiro; balanceia a quantidade; evita devolver a repetida a quem já pegou."""
    prio = sorted([g for g in lista if g["repetida"]], key=lambda g: (-g["vezes"], g["_ts"]))
    resto = sorted([g for g in lista if not g["repetida"]], key=lambda g: g["_ts"])
    carga = {n: [] for n in nomes}
    for g in prio + resto:
        candidatos = list(nomes)
        if g["repetida"] and g["anterior"] and len(nomes) > 1:
            candidatos = [n for n in nomes if n != g["anterior"]["pessoa"]] or candidatos
        n = min(candidatos, key=lambda x: (len(carga[x]), nomes.index(x)))
        carga[n].append(g)
    hoje = date.today().isoformat()
    hist["nomes"] = nomes
    hist["divisoes"][hoje] = {
        "atribuicoes": {g["os"]: {"pessoa": n, "veiculo": g["veiculo"]} for n, gs in carga.items() for g in gs},
        "motivos": motivos}
    salvar(hist)
    return carga




class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/estado":
            return self._json({"nomes": carregar()["nomes"]})
        b = open(os.path.join(PASTA, "index.html"), "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        corpo = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if self.path == "/api/analisar":
                lista = marcar_repetidas(ler_csv(corpo), carregar())
                return self._json({"os": lista})
            if self.path == "/api/dividir":
                d = json.loads(corpo)
                nomes = [n.strip() for n in d["nomes"] if n.strip()]
                if not nomes:
                    return self._json({"erro": "Informe ao menos um nome."}, 400)
                carga = dividir(d["os"], nomes, d.get("motivos", {}), carregar())
                return self._json({"carga": carga})
        except Exception as e:
            return self._json({"erro": str(e)}, 500)
        self._json({"erro": "rota inválida"}, 404)


if __name__ == "__main__":
    print(f"Divisor de O.S. rodando em http://localhost:{PORTA}  (Ctrl+C para sair)")
    try:
        webbrowser.open(f"http://localhost:{PORTA}")
    except Exception:
        pass
    HTTPServer(("127.0.0.1", PORTA), H).serve_forever()
