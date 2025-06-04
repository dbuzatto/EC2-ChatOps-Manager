# EC2-ChatOps-Manager

Este projeto implementa uma função AWS Lambda que atua como um chatbot para gerenciamento de instâncias Amazon EC2. Ele permite que usuários iniciem, parem, verifiquem o status de instâncias e até mesmo agendem ações (iniciar/parar) para horários futuros, tudo através de uma interface de chat (por exemplo, Google Chat, Slack, etc.).

## 🌟 Recursos

* **Controle de Instâncias EC2**: Inicie, pare e verifique o status de instâncias EC2 por ID ou nome (tag 'Name').
* **Agendamento de Ações**: Agende o início ou a parada de instâncias EC2 para um horário específico.
* **Menu Interativo**: Um menu dinâmico com botões para solicitar ações em instâncias EC2.
* **Lista de Agendamentos**: Visualize todos os agendamentos pendentes.
* **Deleção de Agendamentos**: Administradores podem deletar agendamentos.
* **Controle de Acesso**: Permissões baseadas em e-mail para ações restritas (ex: deletar agendamentos ou iniciar/parar certas instâncias).
* **Notificações de Solicitação**: Menciona usuários administrativos em solicitações de ação para instâncias restritas, permitindo um fluxo de aprovação manual.
* **Registro de Ações**: Tags EC2 são atualizadas com o último usuário que executou uma ação e o horário de parada.

---

## 📋 Pré-requisitos

Antes de implantar, certifique-se de ter:

* Uma **Conta AWS** ativa.
* **AWS CLI** configurado e autenticado com permissões adequadas.
* **Python 3.x** instalado.
* **pip** para gerenciamento de pacotes Python.
* Uma plataforma de chat integrada (ex: Google Chat, Slack) configurada para interagir com Webhooks ou AWS API Gateway.

---

## 🛠️ Configuração e Implantação

Siga os passos abaixo para configurar e implantar o bot.

### 1. Configurar Permissões AWS (IAM)

Crie uma **Role IAM** para sua função Lambda com as seguintes permissões:

* `ec2:DescribeInstances`
* `ec2:StartInstances`
* `ec2:StopInstances`
* `ec2:CreateTags`
* `dynamodb:CreateTable` (apenas se você for criar a tabela via CloudFormation/SDK)
* `dynamodb:GetItem`
* `dynamodb:PutItem`
* `dynamodb:DeleteItem`
* `dynamodb:Scan`
* `logs:CreateLogGroup`
* `logs:CreateLogStream`
* `logs:PutLogEvents`

Exemplo de política (substitua `YOUR_AWS_REGION` e `YOUR_ACCOUNT_ID`):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:StartInstances",
                "ec2:StopInstances",
                "ec2:CreateTags"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:DeleteItem",
                "dynamodb:Scan"
            ],
            "Resource": "arn:aws:dynamodb:YOUR_AWS_REGION:YOUR_ACCOUNT_ID:table/EC2InstanceSchedules"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        }
    ]
}