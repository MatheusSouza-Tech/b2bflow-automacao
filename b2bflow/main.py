import os
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_BASE_URL = os.getenv("ZAPI_BASE_URL", "https://api.z-api.io")


def validar_variaveis():
    obrigatorias = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        "ZAPI_INSTANCE_ID": ZAPI_INSTANCE_ID,
        "ZAPI_TOKEN": ZAPI_TOKEN,
        "ZAPI_CLIENT_TOKEN": ZAPI_CLIENT_TOKEN,
    }

    faltando = [nome for nome, valor in obrigatorias.items() if not valor]

    if faltando:
        raise ValueError(
            f"As seguintes variáveis estão faltando no .env: {', '.join(faltando)}"
        )


def criar_cliente_supabase():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def normalizar_telefone(phone):
    return "".join(ch for ch in str(phone) if ch.isdigit())


def buscar_contatos(supabase):
    response = (
        supabase
        .table("contatos")
        .select("id,nome_contato,phone,enviado")
        .eq("enviado", False)
        .limit(3)
        .execute()
    )

    return response.data or []


def enviar_mensagem_zapi(phone, message):
    url = f"{ZAPI_BASE_URL}/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"

    headers = {
        "Client-Token": ZAPI_CLIENT_TOKEN,
        "Content-Type": "application/json",
    }

    payload = {
        "phone": phone,
        "message": message,
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)

    if not response.ok:
        raise RuntimeError(
            f"Falha ao enviar pela Z-API. Status: {response.status_code}. Resposta: {response.text}"
        )

    try:
        return response.json()
    except ValueError:
        return {"raw_response": response.text}


def marcar_como_enviado(supabase, contato_id):
    (
        supabase
        .table("contatos")
        .update({
            "enviado": True,
            "enviado_em": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", contato_id)
        .execute()
    )


def processar_contato(supabase, contato):
    contato_id = contato["id"]
    nome_contato = (contato.get("nome_contato") or "").strip()
    phone = normalizar_telefone(contato.get("phone", ""))

    if not nome_contato:
        logging.warning(f"Contato ID {contato_id} ignorado: nome vazio.")
        return False

    if not phone:
        logging.warning(f"Contato ID {contato_id} ignorado: telefone inválido.")
        return False

    mensagem = f"Olá, {nome_contato} tudo bem com você?"

    logging.info(f"Iniciando envio para {nome_contato} ({phone})...")

    try:
        retorno = enviar_mensagem_zapi(phone, mensagem)
        logging.info(f"Mensagem enviada com sucesso para {nome_contato}. Retorno: {retorno}")

        try:
            marcar_como_enviado(supabase, contato_id)
            logging.info(f"Contato ID {contato_id} marcado como enviado no Supabase.")
        except Exception as erro_update:
            logging.error(
                f"A mensagem foi enviada para {nome_contato}, mas houve erro ao atualizar o Supabase: {erro_update}"
            )
            return False

        return True

    except Exception as erro_envio:
        logging.error(f"Falha ao enviar mensagem para {nome_contato}: {erro_envio}")
        return False


def main():
    try:
        validar_variaveis()
        supabase = criar_cliente_supabase()

        logging.info("Conexão com Supabase criada com sucesso.")

        contatos = buscar_contatos(supabase)

        if not contatos:
            logging.info("Nenhum contato pendente encontrado para envio.")
            return

        logging.info(f"Foram encontrados {len(contatos)} contato(s) para processar.")

        enviados = 0
        falhas = 0

        for contato in contatos:
            sucesso = processar_contato(supabase, contato)
            if sucesso:
                enviados += 1
            else:
                falhas += 1

        logging.info(
            f"Processo finalizado. Enviados com sucesso: {enviados}. Falhas: {falhas}."
        )

    except Exception as erro:
        logging.exception(f"Erro crítico na execução do sistema: {erro}")


if __name__ == "__main__":
    main()