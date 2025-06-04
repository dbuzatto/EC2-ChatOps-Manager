import boto3
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
ec2 = boto3.client('ec2')
tabela = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])

def lambda_handler(event, context):
    now_utc = datetime.now(timezone.utc).isoformat()
    response = tabela.scan(
        FilterExpression="#s = :pendente AND horario <= :agora",
        ExpressionAttributeNames={
            "#s": "status"
        },
        ExpressionAttributeValues={
            ":pendente": "pendente",
            ":agora": now_utc
        }
    )

    agendamentos = response.get("Items", [])
    logger.info(f"{len(agendamentos)} agendamento(s) a processar")

    for ag in agendamentos:
        try:
            instancia_id = ag["instancia"]
            acao = ag["acao"]
            ag_id = ag["id"]

            if acao == "start":
                ec2.start_instances(InstanceIds=[instancia_id])
            elif acao == "stop":
                ec2.stop_instances(InstanceIds=[instancia_id])
            else:
                raise ValueError("Ação inválida")

            tabela.update_item(
                Key={"id": ag_id},
                UpdateExpression="SET #s = :ok",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":ok": "executado"}
            )
            logger.info(f"Ação {acao} aplicada à instância {instancia_id}")
        except Exception as e:
            logger.error(f"Erro no agendamento {ag.get('id')}: {str(e)}")
            tabela.update_item(
                Key={"id": ag.get("id")},
                UpdateExpression="SET #s = :erro",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":erro": "erro"}
            )