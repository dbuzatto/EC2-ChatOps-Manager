# EC2 Instance Manager via ChatBot (Lambda)

Este projeto permite gerenciar instâncias EC2 da AWS por meio de comandos em um bot de chat (ex: Google Chat). Os usuários podem iniciar, parar e agendar ações em instâncias de forma segura e com controle de permissões.

## 🧩 Funcionalidades

- ✅ **Start/Stop** de instâncias EC2 via comandos (`start`, `stop`)
- 🕒 **Agendamentos** de ações (ex: `agendar start serverservice 22:30`)
- 📋 **Listagem de agendamentos pendentes**
- 👮‍♂️ **Controle de permissões** (usuários restritos/admins)
- 📣 **Menções a administradores** para aprovação de ações
- 📦 Integração com **DynamoDB** para persistência de agendamentos
- 🖱️ **Menu interativo** para seleção e solicitação de ações (botões)
- ⏱️ Relatório de **tempo de uptime** e logs de ações

## 🚀 Exemplo de Comandos

### Comandos diretos:
```bash
start serverservice
stop i-0abc1234def567890
status test-env
```

### Agendamento:
```bash
agendar start serverservice 22:00
agendar stop i-0abc1234def567890 03:30
```

### Outros:
```bash
menu                 # Mostra todas as instâncias com botões
agendamentos         # Lista agendamentos pendentes
deletar agendamento <ID>  # (admins apenas)
```

## ⚙️ Pré-requisitos

- AWS Lambda com permissões para EC2 e DynamoDB
- Tabela DynamoDB chamada `EC2InstanceSchedules`
- Configuração de webhook no Google Chat ou outra plataforma compatível
- Ambiente Python 3.9+

## 🛡️ Permissões

- **ALLOWED_ADMIN_USERS**: e-mails com permissão para comandos irrestritos e deletar agendamentos
- **UNRESTRICTED_INSTANCES_BY_NAME**: nomes de instâncias que podem ser controladas por qualquer usuário

## 🧱 Estrutura do DynamoDB

| Campo        | Tipo     | Descrição                          |
|--------------|----------|------------------------------------|
| id           | string   | ID único do agendamento (UUID)     |
| instancia    | string   | ID da instância EC2                |
| acao         | string   | `start` ou `stop`                  |
| horario      | string   | ISO 8601 (UTC) do agendamento      |
| solicitante  | string   | e-mail de quem solicitou           |
| status       | string   | `pendente`, `executado`, etc       |

## 📝 Observações

- Os horários inseridos no comando `agendar` devem estar no formato `HH:mm` (horário local UTC-3).
- Se o horário já passou no dia atual, a ação será agendada para o dia seguinte.
- Todas as ações são registradas via tags na própria instância (`LastActionBy`, `StoppedAt`).

## 📦 Deploy

1. Faça upload do código no Lambda
2. Configure a variável de ambiente `DYNAMODB_TABLE_NAME`
3. Crie a tabela no DynamoDB conforme estrutura acima
4. Conecte o Lambda a um Webhook do Google Chat (via API Gateway se necessário)

## 📄 Licença

Este projeto é open-source sob a licença MIT.