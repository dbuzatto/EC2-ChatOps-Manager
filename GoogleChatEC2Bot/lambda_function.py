import json
import boto3
import logging
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Inicializa clientes AWS
ec2 = boto3.client('ec2')
dynamodb = boto3.resource('dynamodb')

# Nome da tabela DynamoDB para agendamentos (substitua pelo seu nome de tabela)
DYNAMODB_TABLE_NAME = 'EC2InstanceSchedules' 
tabela_agendamentos = dynamodb.Table(DYNAMODB_TABLE_NAME)

# --- Configurações de Usuários e Permissões (PERSONALIZÁVEL) ---
# Lista de e-mails de usuários permitidos para ações restritas (ex: deletar agendamentos)
ALLOWED_ADMIN_USERS = ["admin.user@example.com", "another.admin@example.com"]

# Informações de usuários para menções em plataformas de chat (se aplicável)
# Adapte conforme a plataforma de chat (ex: Google Chat, Slack). 
# Para Google Chat, 'name' é o ID do usuário (geralmente "users/ID_NUMERICO")
# Para outras plataformas, você pode precisar de IDs de usuário ou ignorar se não usar menções.
MENTIONABLE_USERS = [
    {"name": "users/YOUR_FIRST_USER_ID", "displayName": "First User Display"},
    {"name": "users/YOUR_SECOND_USER_ID", "displayName": "Second User Display"}
]

# Lista de nomes de instâncias EC2 que NÃO exigem permissão de administrador para start/stop
# Ex: instâncias de desenvolvimento ou testes
UNRESTRICTED_INSTANCES_BY_NAME = ["dev-server", "test-env"]


def response(msg, card_data=None):
    """
    Constrói a resposta formatada para a plataforma de chat.
    Pode ser texto simples ou um card (para o menu ou lista de agendamentos).
    """
    if card_data:
        return {
            'statusCode': 200,
            'body': json.dumps(card_data),
            'headers': {'Content-Type': 'application/json'}
        }
    else:
        return {
            'statusCode': 200,
            'body': json.dumps({'text': msg}),
            'headers': {'Content-Type': 'application/json'}
        }

def get_instance_name_from_id(instance_id):
    """Obtém o nome da tag 'Name' de uma instância EC2 dado seu ID."""
    try:
        res = ec2.describe_instances(InstanceIds=[instance_id])
        if res['Reservations']:
            tags = {tag['Key']: tag['Value'] for tag in res['Reservations'][0]['Instances'][0].get('Tags', [])}
            return tags.get('Name', instance_id)
    except Exception as e:
        logger.warning(f"Não foi possível obter o nome da instância {instance_id}: {e}")
    return instance_id # Retorna o ID se o nome não for encontrado ou houver erro

def mention_admin_users(requester_name, action, instance_identifier):
    """
    Cria uma mensagem para mencionar usuários administrativos 
    quando uma ação que requer aprovação é solicitada.
    """
    mention_tokens = []
    annotations = []
    start_index = 0

    for user in MENTIONABLE_USERS:
        token = f"<{user['name']}>"
        mention_tokens.append(token)
        annotations.append({
            "type": "USER_MENTION",
            "startIndex": start_index,
            "length": len(token),
            "userMention": {
                "user": {
                    "name": user['name'],
                    "displayName": user['displayName'],
                    "type": "HUMAN"
                },
                "type": "MENTION"
            }
        })
        start_index += len(token) + 2 # +2 para a vírgula e espaço

    mensagem = ", ".join(mention_tokens) + f", {requester_name} solicitou que você {action} a instância {instance_identifier}."

    return response(mensagem, card_data={
        "text": mensagem,
        "annotations": annotations,
        "actionResponse": {"type": "NEW_MESSAGE"}
    })

def build_instance_menu():
    """
    Constrói um card com botões para iniciar/parar instâncias, 
    buscando todas as instâncias EC2.
    """
    res = ec2.describe_instances()
    widgets = []

    for r in res['Reservations']:
        for inst in r['Instances']:
            instance_id = inst['InstanceId']
            state = inst['State']['Name']
            tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
            name = tags.get('Name', instance_id)

            widgets.append({
                "textParagraph": {
                    "text": f"<b>{name}</b> ({instance_id}) - {state}"
                }
            })

            # Botão para solicitar ação (start/stop)
            action_name = f"solicitar_start_{instance_id}" if state != 'running' else f"solicitar_stop_{instance_id}"
            action_text = "Solicitar LIGAR" if state != 'running' else "Solicitar DESLIGAR"

            widgets.append({
                "buttons": [
                    {
                        "textButton": {
                            "text": action_text,
                            "onClick": {
                                "action": {
                                    "actionMethodName": action_name
                                }
                            }
                        }
                    }
                ]
            })

    card = {
        'cards': [
            {
                'header': {
                    'title': 'Menu de Instâncias EC2',
                    'subtitle': 'Clique para solicitar uma ação'
                },
                'sections': [
                    {
                        'widgets': widgets
                    }
                ]
            }
        ]
    }
    return response(None, card)

def list_scheduled_tasks(requesting_user_email):
    """
    Lista todos os agendamentos pendentes de ações em instâncias EC2.
    Permite deletar agendamentos para usuários permitidos.
    """
    try:
        response_db = tabela_agendamentos.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('status').eq('pendente')
        )
        agendamentos = response_db['Items']

        if not agendamentos:
            return response("📋 Não há agendamentos pendentes no momento.")

        # Obtém nomes das instâncias para melhor exibição
        instance_ids = [a['instancia'] for a in agendamentos]
        instance_names = {}
        if instance_ids:
            try:
                res = ec2.describe_instances(InstanceIds=instance_ids)
                for r in res['Reservations']:
                    for inst in r['Instances']:
                        tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                        instance_names[inst['InstanceId']] = tags.get('Name', inst['InstanceId'])
            except Exception as e:
                logger.warning(f"Não foi possível obter nomes das instâncias: {e}")

        card_sections = []
        sorted_agendamentos = sorted(agendamentos, key=lambda x: x['horario'])

        for agendamento in sorted_agendamentos:
            horario_utc = datetime.fromisoformat(agendamento['horario'])
            # Ajuste o timezone conforme sua região (ex: UTC-3 para Brasília)
            horario_local = horario_utc.astimezone(timezone(timedelta(hours=-3))) 
            
            instance_display_name = instance_names.get(agendamento['instancia'], agendamento['instancia'])
            
            requester_email = agendamento.get('solicitante', 'desconhecido@example.com')
            requester_display = requester_email.split('@')[0] # Nome simples do e-mail

            widgets = []
            widgets.append({
                "textParagraph": {
                    "text": (f"<b>{horario_local.strftime('%d/%m %H:%M')}</b> | "
                             f"<b>{agendamento['acao'].upper()}</b> | "
                             f"{instance_display_name} ({agendamento['instancia']})\n"
                             f"<i>Solicitado por: {requester_display}</i>")
                }
            })

            # Adiciona botão de deletar apenas para usuários com permissão
            if requesting_user_email in ALLOWED_ADMIN_USERS:
                widgets.append({
                    "buttons": [
                        {
                            "textButton": {
                                "text": "Deletar",
                                "onClick": {
                                    "action": {
                                        "actionMethodName": f"deletar_agendamento_{agendamento['id']}"
                                    }
                                }
                            }
                        }
                    ]
                })
            
            card_sections.append({
                'widgets': widgets
            })
        
        if not card_sections:
            return response("📋 Não há agendamentos pendentes no momento.")

        card = {
            'cards': [
                {
                    'header': {
                        'title': '📋 Agendamentos Pendentes',
                        'subtitle': 'Gerencie seus agendamentos'
                    },
                    'sections': card_sections
                }
            ]
        }
        return response(None, card)

    except Exception as e:
        logger.error("Erro ao listar agendamentos:", exc_info=True)
        return response(f"Erro ao listar agendamentos: {str(e)}")

def delete_scheduled_task(schedule_id):
    """Deleta um agendamento específico do DynamoDB."""
    try:
        response_get = tabela_agendamentos.get_item(Key={'id': schedule_id})
        item = response_get.get('Item')

        if not item:
            return response(f"❌ Agendamento com ID '{schedule_id}' não encontrado.")
        
        if item.get('status') != 'pendente':
            return response(f"❌ Agendamento com ID '{schedule_id}' não está mais pendente ou já foi processado.")

        tabela_agendamentos.delete_item(Key={'id': schedule_id})
        return response(f"✅ Agendamento '{schedule_id}' deletado com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao deletar agendamento {schedule_id}:", exc_info=True)
        return response(f"Erro ao deletar agendamento '{schedule_id}': {str(e)}")

def lambda_handler(event, context):
    """
    Função principal do AWS Lambda que processa os eventos.
    """
    try:
        logger.info("Evento recebido:")
        logger.info(json.dumps(event))

        if 'body' not in event:
            return response("⚠️ Evento inválido: sem body.")
        body = json.loads(event['body'])

        action_method = body.get('action', {}).get('actionMethodName')
        user_info = body.get('user', {})
        user_name = user_info.get('displayName', 'Um usuário')
        user_email = user_info.get('email', '').lower()
        user_id = user_info.get('name', '') # Pode ser usado para menções em algumas plataformas

        if action_method:
            logger.info(f"Ação de botão recebida: {action_method}")

            if action_method.startswith("solicitar_start_"):
                instance_id = action_method.replace("solicitar_start_", "")
                # Menciona admins para aprovação de start
                return mention_admin_users(user_name, "LIGAR", get_instance_name_from_id(instance_id))

            elif action_method.startswith("solicitar_stop_"):
                instance_id = action_method.replace("solicitar_stop_", "")
                # Menciona admins para aprovação de stop
                return mention_admin_users(user_name, "DESLIGAR", get_instance_name_from_id(instance_id))
            
            elif action_method.startswith("deletar_agendamento_"):
                if user_email not in ALLOWED_ADMIN_USERS:
                    return response("🚫 Você não tem permissão para deletar agendamentos.")
                schedule_id = action_method.replace("deletar_agendamento_", "")
                return delete_scheduled_task(schedule_id)

            return response("❓ Ação de botão não reconhecida.")

        # Processamento de comandos de texto (se não for uma ação de botão)
        sender_info = body.get('message', {}).get('sender', {})
        user_name = sender_info.get('displayName', 'desconhecido')
        user_email = sender_info.get('email', '').lower()

        message = body.get('argumentText', '').strip().lower()
        if not message:
            # Se não há argumentText (e.g., mensagem direta ou com menção no início)
            text_raw = body.get('message', {}).get('text', '').lower()
            # Remove menções do bot para extrair o comando limpo
            for a in body.get('message', {}).get('annotations', []):
                if a.get('type') == 'USER_MENTION':
                    start = a.get('startIndex', 0)
                    length = a.get('length', 0)
                    text_raw = (text_raw[:start] + text_raw[start + length:]).strip()
                    break
            message = text_raw

        logger.info(f"Mensagem processada: '{message}'")
        parts = message.split()

        # Comando: agendar <acao> <instancia> <hora> (formato 24h: HH:mm)
        if message.startswith("agendar "):
            agendar_parts = message.split()
            if len(agendar_parts) != 4:
                return response("Uso correto: agendar <start|stop> <nome ou id da instância> <HH:mm>")

            _, action, target, time_str = agendar_parts
            action = action.lower()

            if action not in ["start", "stop"]:
                return response("Ação inválida. Use 'start' ou 'stop'.")

            try:
                # O timezone aqui deve corresponder ao fuso horário que você espera para a entrada do usuário
                # Ex: UTC-3 para Brasília. Ajuste conforme sua necessidade.
                local_time = datetime.strptime(time_str, "%H:%M")
                now_local = datetime.now(timezone(timedelta(hours=-3))) 
                scheduled_local = now_local.replace(hour=local_time.hour, minute=local_time.minute, second=0, microsecond=0)
                
                # Se o horário agendado já passou para hoje, agenda para o dia seguinte
                if scheduled_local < now_local:
                    scheduled_local += timedelta(days=1)
                
                # Converte para UTC para armazenamento no DynamoDB
                scheduled_utc = scheduled_local.astimezone(timezone.utc).isoformat()
            except ValueError:
                return response("Horário inválido. Use o formato HH:mm (ex: 22:30).")

            instance_id = None
            if target.startswith("i-"): # Busca por ID de instância
                try:
                    res = ec2.describe_instances(InstanceIds=[target])
                    if res['Reservations']:
                        instance_id = target
                except Exception as e:
                    logger.warning(f"Instância com ID {target} não encontrada: {e}")
            else: # Busca por tag 'Name'
                res = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': [target]}])
                for r in res['Reservations']:
                    for inst in r['Instances']:
                        tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                        if tags.get('Name', '').lower() == target.lower():
                            instance_id = inst['InstanceId']
                            break
                    if instance_id:
                        break

            if not instance_id:
                return response(f"Instância '{target}' não encontrada por ID ou Name.")

            schedule_id = str(uuid.uuid4())

            item = {
                "id": schedule_id,
                "instancia": instance_id,
                "acao": action,
                "horario": scheduled_utc,
                "solicitante": user_email, 
                "status": "pendente"
            }

            tabela_agendamentos.put_item(Item=item)

            return response(f"✅ Agendamento registrado com sucesso!\n🕒 Horário UTC-3: {scheduled_local.strftime('%d/%m %H:%M')}\n💻 Instância: {instance_id}\n⚙️ Ação: {action.upper()}")

        if message == "menu":
            return build_instance_menu()
            
        if message == "agendamentos":
            return list_scheduled_tasks(user_email)
            
        # Comando para deletar agendamento via texto (alternativa ao botão)
        if message.startswith("deletar agendamento "):
            if user_email not in ALLOWED_ADMIN_USERS:
                return response("🚫 Você não tem permissão para deletar agendamentos.")
            try:
                schedule_id = message.split("deletar agendamento ")[1].strip()
                return delete_scheduled_task(schedule_id)
            except IndexError:
                return response("Uso correto: deletar agendamento <ID_DO_AGENDAMENTO>")

        # Processamento de comandos diretos (start, stop, status)
        if len(parts) != 2:
            return response("Comando inválido. Use:\n- start <id/nome>\n- stop <id/nome>\n- status <id/nome>\n- agendar <start|stop> <id/nome> <HH:mm>\n- agendamentos\n- menu")

        command, target = parts

        # Verifica se a instância é restrita e se o usuário tem permissão
        is_restricted_instance = True
        if not target.startswith("i-"): # Se for por nome, verifica se está na lista de não restritas
            instance_name_from_target = target.lower()
            if instance_name_from_target in UNRESTRICTED_INSTANCES_BY_NAME:
                is_restricted_instance = False

        if command in ["start", "stop"] and user_email not in ALLOWED_ADMIN_USERS and is_restricted_instance:
            return response(f"🚫 Acesso negado: {user_email} não está autorizado a executar '{command}' para esta instância. Para solicitar, use os botões do menu ou entre em contato com um administrador.")

        # Verifica se o bot foi mencionado (se aplicável à sua plataforma de chat)
        annotations = body.get('message', {}).get('annotations', [])
        bot_mentioned = any(a.get('type') == 'USER_MENTION' for a in annotations)
        # Ajuste esta lógica se seu bot não exige menção ou se a forma de menção é diferente
        # if command in ["start", "stop", "status"] and not bot_mentioned:
        #     return response("Por favor, mencione o bot com @SeuBot ao usar comandos como start, stop ou status.")


        # Busca a instância pelo ID ou nome
        instance = None
        if target.startswith("i-"):
            try:
                res = ec2.describe_instances(InstanceIds=[target])
                if res['Reservations']:
                    instance = res['Reservations'][0]['Instances'][0]
            except Exception as e:
                logger.warning(f"Instância com ID {target} não encontrada: {e}")
        else:
            res = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': [target]}])
            for r in res['Reservations']:
                for inst in r['Instances']:
                    tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                    name_tag = tags.get('Name', '').lower()
                    if name_tag == target.lower():
                        instance = inst
                        break
                if instance:
                    break
        
        if not instance:
            return response(f"Nenhuma instância encontrada com o identificador '{target}'.")

        instance_id = instance['InstanceId']

        if command == "start":
            ec2.start_instances(InstanceIds=[instance_id])
            # Adiciona tags para rastreamento de quem iniciou e quando
            ec2.create_tags(Resources=[instance_id], Tags=[{
                'Key': 'LastActionBy',
                'Value': f"{user_name} - start"
            }])
            return response(f"🚀 Instância {instance_id} iniciada por {user_name}.")

        elif command == "stop":
            now = datetime.now(timezone(timedelta(hours=-3))).isoformat() # Armazena o tempo em UTC-3
            ec2.stop_instances(InstanceIds=[instance_id])
            # Adiciona tags para rastreamento de quem parou e quando
            ec2.create_tags(Resources=[instance_id], Tags=[
                {'Key': 'LastActionBy', 'Value': f"{user_name} - stop"},
                {'Key': 'StoppedAt', 'Value': now}
            ])
            return response(f"🛑 Instância {instance_id} desligada por {user_name}.")

        elif command == "status":
            state = instance['State']['Name']
            launch_time = instance.get('LaunchTime')
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            last_action = tags.get('LastActionBy', 'Indefinido')
            stopped_at_str = tags.get('StoppedAt')

            msg = f"📊 Status da instância {instance_id}: {state}\n👤 Última ação: {last_action}"

            if state == 'running' and launch_time:
                now_local = datetime.now(timezone(timedelta(hours=-3)))
                launch_time_local = launch_time.astimezone(timezone(timedelta(hours=-3)))
                uptime = now_local - launch_time_local
                hours = int(uptime.total_seconds() // 3600)
                minutes = int((uptime.total_seconds() % 3600) // 60)
                msg += f"\n⏱ Ligada há {hours}h {minutes}min"

            elif state == 'stopped' and stopped_at_str:
                try:
                    stopped_at = datetime.fromisoformat(stopped_at_str).astimezone(timezone(timedelta(hours=-3)))
                    if launch_time:
                        launch_time_local_at_stop = launch_time.astimezone(timezone(timedelta(hours=-3)))
                        time_running_before_stop = stopped_at - launch_time_local_at_stop
                        hours = int(time_running_before_stop.total_seconds() // 3600)
                        minutes = int((time_running_before_stop.total_seconds() % 3600) // 60)
                        msg += f"\n🛑 Parada em: {stopped_at.strftime('%d/%m/%Y %H:%M')}"
                        msg += f"\n⏱ Ficou ligada por: {hours}h {minutes}min"
                except Exception:
                    msg += "\n⚠️ Erro ao processar o horário de parada."

            return response(msg)

        return response("Comando não reconhecido.")

    except Exception as e:
        logger.error("Erro ao processar comando:", exc_info=True)
        return response(f"Erro ao processar comando: {str(e)}")