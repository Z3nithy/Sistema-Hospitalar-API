# API hospitalar — protótipo

Uma API para estudar o funcionamento de um sistema hospitalar: cadastro de pacientes e profissionais, agenda, internações, registros clínicos, estoque, faturamento e convênios simulados. A aplicação fornece uma API HTTP, não uma interface de gestão; você pode explorá-la pelo navegador usando a documentação interativa.

> **Atenção:** este projeto é um protótipo para portfólio. Use somente **dados fictícios**. Ele não está pronto para atendimento clínico ou produção: faltam, entre outros requisitos, gestão de consentimento, validação clínica, auditoria resistente a alterações e revisão de segurança e conformidade com a LGPD.

## Índice

- [Tecnologias e funcionalidades](#tecnologias-e-funcionalidades)
- [Como instalar e executar](#como-instalar-e-executar)
- [Primeiros passos na API](#primeiros-passos-na-api)
- [Configuração](#configuração)
- [Autenticação e permissões](#autenticação-e-permissões)
- [Recursos e regras de negócio](#recursos-e-regras-de-negócio)
- [Convênios e operadora simulada](#convênios-e-operadora-simulada)
- [Monitoramento e backup SQLite](#monitoramento-e-backup-sqlite)
- [Banco e evolução](#banco-e-evolução)
- [Demonstração com dados fictícios](#demonstração-com-dados-fictícios)
- [Testes e qualidade](#testes-e-qualidade)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Dúvidas frequentes](#dúvidas-frequentes)
- [Licença](#licença)

## Tecnologias e funcionalidades

O projeto usa **Python**, **FastAPI** para as rotas, **SQLAlchemy** para acesso aos dados, **SQLite** como banco local, **Alembic** para migrações e **JWT** para autenticação. Os testes usam Pytest e a verificação de código usa Ruff.

| Área | O que é possível demonstrar |
| --- | --- |
| Cadastros e agenda | Pacientes, profissionais, disponibilidade e consultas |
| Atendimento | Prontuários, alergias, diagnósticos, evoluções, prescrições e exames |
| Internação | Leitos, internações e altas |
| Estoque | Medicamentos, lotes, validades, movimentações e alertas |
| Financeiro e convênios | Cobranças, pagamentos manuais e autorizações e guias simuladas |
| Segurança e operação | Perfis, restrições, auditoria, monitoramento e backup SQLite |

As integrações de convênio são locais e simuladas. Não há cobrança, pagamento ou comunicação com operadora real.

## Como instalar e executar

### Pré-requisitos

- Python instalado. A configuração de CI contempla Python **3.12 e 3.14**.
- Terminal na pasta raiz do projeto e acesso à internet para instalar as dependências.
- Não é necessário instalar ou iniciar um servidor de banco: o SQLite cria um arquivo local.

Confira a versão do Python com `python --version`. Os comandos abaixo usam **PowerShell no Windows**. Em Linux ou macOS, use `python3` se necessário, ative o ambiente com `source .venv/bin/activate` e copie o arquivo de configuração com `cp .env.example .env`.

### 1. Prepare o ambiente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

O ambiente virtual mantém as dependências do projeto separadas das demais. O arquivo `requirements-dev.txt` inclui tanto as dependências da API quanto as ferramentas de teste e lint.

### 2. Configure a chave da aplicação

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Abra o `.env`, substitua o valor de `SECRET_KEY` pela chave gerada e salve. Ela deve ter pelo menos 32 caracteres; mantenha-a privada e não envie o arquivo `.env` para o repositório. As outras opções podem permanecer com os valores de exemplo para execução local.

### 3. Prepare o banco e o administrador

```powershell
python -m alembic upgrade head
python criar_admin.py --nome "Administrador" --login admin
```

A migração cria ou atualiza as tabelas; iniciar a aplicação **não** as cria automaticamente. O segundo comando solicita uma senha de pelo menos 8 caracteres e sua confirmação sem exibi-las. Não existe conta ou senha padrão. Se já tiver um banco com dados, faça [backup](#monitoramento-e-backup-sqlite) antes de aplicar novas migrações.

### 4. Inicie a API

```powershell
python -m uvicorn main:app --reload --no-access-log --no-proxy-headers
```

Mantenha o terminal aberto e acesse:

- **Documentação interativa:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Aplicação respondendo:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Banco disponível e atualizado:** [http://127.0.0.1:8000/health/ready](http://127.0.0.1:8000/health/ready)

Para encerrar o servidor, pressione `Ctrl+C` no terminal. Em outra sessão de terminal, ative novamente o ambiente virtual antes de executar os comandos do projeto.

## Primeiros passos na API

Com o servidor em execução, abra `/docs` e siga este exemplo com dados fictícios:

1. Abra `POST /auth/login`, clique em **Try it out** e informe o login e a senha criados no passo anterior:

   ```json
   {
     "login": "admin",
     "senha": "sua-senha"
   }
   ```

2. Clique em **Execute** e copie o valor de `access_token` da resposta. Clique em **Authorize**, cole apenas o token no campo e confirme. O navegador passará a enviá-lo nas requisições protegidas.
3. Abra `POST /pacientes`, clique em **Try it out** e envie:

   ```json
   {
     "nome": "Paciente ficticio",
     "documento": "DEMO-001",
     "nascimento": "1990-01-01",
     "telefone": null
   }
   ```

4. Uma resposta `201` contém o paciente criado e seu `id`. Em seguida, execute `GET /pacientes` para listá-lo. Se o documento já estiver cadastrado, use outro valor fictício.

`GET` consulta dados; `POST` normalmente cria um registro ou executa uma ação; `PUT` atualiza dados. Na documentação interativa, cada operação mostra os campos, tipos e respostas aceitos. Para testar sem cadastrar os dados iniciais manualmente, veja a [demonstração](#demonstração-com-dados-fictícios).

## Configuração

As opções podem ser definidas no `.env`; variáveis de ambiente também podem sobrescrever esses valores. O arquivo `.env.example` contém apenas valores de exemplo.

| Variável | Padrão | Finalidade |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./database.db` | Caminho do banco SQLite local |
| `SECRET_KEY` | Obrigatória | Chave privada dos tokens e do identificador de limite de login; mínimo de 32 caracteres |
| `ALGORITHM` | `HS256` | Algoritmo de assinatura dos tokens |
| `DEBUG` | `false` | Modo de depuração; mantenha desativado em ambientes compartilhados |
| `SQLITE_WAL` | `false` | Ativa o modo WAL no SQLite, quando suportado |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | Tempo de espera por bloqueios, em milissegundos; de 1 a 60000 |

## Autenticação e permissões

## Autenticação

Envie `POST /auth/login` com `{"login":"admin","senha":"sua-senha"}`. Use o `access_token` retornado no cabeçalho `Authorization: Bearer <token>`; ele expira após 60 minutos. `GET /auth/me` mostra o usuário atual. Somente administradores podem criar e listar usuários em `/usuarios`. Os perfis aceitos são `admin`, `medico`, `enfermagem` e `recepcao`.

`POST /auth/logout` revoga **todas** as sessões do usuário, inclusive a atual; um novo login gera outro token. Tokens antigos, sem a versão de revogação, são recusados após a migração. Para recuperação de senha, um operador com acesso local autorizado pode executar `python redefinir_senha.py --login usuario`; o comando solicita a nova senha sem exibi-la e revoga todas as sessões do usuário. Não há recuperação por e-mail.

Cinco tentativas inválidas consecutivas do mesmo endereço em 15 minutos bloqueiam novos logins desse endereço por 15 minutos; durante o bloqueio a API responde 429 com `Retry-After`. Um login bem-sucedido antes do bloqueio limpa as falhas. O controle é compartilhado pelo banco e guarda um identificador HMAC do endereço, não o IP em texto. Não usa diretamente cabeçalhos de proxy; mantenha `--no-proxy-headers` no Uvicorn para impedir que cabeçalhos não confiáveis alterem a identidade. Atrás de proxy, os clientes podem aparecer como um único endereço e compartilhar o bloqueio. Registros expirados são removidos quando ocorrem novas falhas. Essa proteção é básica e não substitui controles de infraestrutura.

O administrador deve cadastrar o profissional e vincular o usuário clínico por `PUT /usuarios/{id}/profissional`, com `{"profissional_id": 1}`. Um profissional só pode estar associado a um usuário. Médicos e profissionais de enfermagem só veem pacientes que estejam vinculados ao seu profissional; médicos só podem criar registros clínicos ou concluir consultas em seu próprio nome. O administrador tem acesso geral; a recepção acessa cadastros e consultas, mas não prontuários, prescrições ou resultados.

Uma consulta cria automaticamente o vínculo entre paciente e profissional agendado; uma internação o cria para o profissional responsável informado. A criação e o vínculo são transacionais. Para internar, médicos e enfermagem precisam já ter vínculo com o paciente e informar o próprio profissional; o administrador pode iniciar a internação e indicar outro profissional. O vínculo permanece após cancelamento ou alta. O administrador também pode criar, listar e remover vínculos em `/vinculos`.

### Restrições por operação

O administrador consulta os nomes disponíveis em `GET /operacoes` e as restrições de um usuário em `GET /usuarios/{id}/permissoes`. Para bloquear uma operação, use `PUT /usuarios/{id}/permissoes/{operacao}` com `{"permitida":false}`; use `true` para remover o bloqueio. Por padrão não há bloqueios adicionais. Eles se aplicam somente a usuários não administradores e **não concedem** acesso além do perfil ou do vínculo com o paciente.

Para bloquear um recurso em conjunto, use `GET /usuarios/{id}/recursos` para listar os recursos e `PUT /usuarios/{id}/recursos/{recurso}` com `{"permitida":false}`; use `true` para remover o bloqueio. Ele cobre as rotas mapeadas que expõem o recurso, incluindo histórico e administração quando aplicável. Bloquear `pacientes` também bloqueia operações de consulta, atendimento, faturamento, carteirinhas, autorizações e guias vinculadas a pacientes. O recurso `convenios` bloqueia o catálogo de convênios, planos, procedimentos, coberturas, carteirinhas, autorizações e guias, mas não as cobranças e pagamentos existentes. O histórico completo é negado se qualquer categoria que ele reúne estiver bloqueada.

As restrições por operação continuam independentes: bloquear uma leitura individual não bloqueia automaticamente listagem ou outras operações relacionadas. As duas camadas mantêm os limites dos perfis e vínculos existentes; administradores não podem ser restringidos por elas. `/auth/me` e `/auth/logout` não são restringíveis. Novas rotas clínicas precisam ser incluídas no mapa de recursos e nos testes.

## Recursos e regras de negócio

Os recursos de negócio exigem autenticação. A maioria das listagens aceita `offset` (quantos registros pular, padrão 0) e `limit` (quantos retornar, padrão 50 e máximo 100). A documentação interativa descreve os campos, filtros e formatos de entrada e saída de cada operação.

| Recurso | Operações | Leitura | Escrita |
| --- | --- | --- | --- |
| `/pacientes` | Criar, listar, obter por ID e atualizar com PUT | Todos os perfis | Admin e recepção |
| `/profissionais` | Criar, listar, obter e atualizar com PUT | Todos | Admin |
| `/consultas` | Criar, listar, obter, cancelar e concluir | Todos, com filtro de vínculo para perfis clínicos | Agendar/cancelar: admin e recepção; concluir: admin e médico responsável |
| `/prontuarios` | Criar, listar e obter | Admin, médico e enfermagem | Admin e médico |
| `/leitos` | Criar, listar, obter e atualizar com PUT | Todos | Admin |
| `/internacoes` | Criar, listar, obter e dar alta | Admin, médico e enfermagem | Internar: admin, médico e enfermagem; alta: admin e médico |
| `/prescricoes` | Criar, listar e obter | Admin, médico e enfermagem | Admin e médico |
| `/exames` | Criar, listar, obter e registrar resultado | Admin, médico e enfermagem | Admin e médico |
| `/alergias` | Criar, listar e obter agente, reação e gravidade | Admin, médico e enfermagem | Admin, médico e enfermagem |
| `/diagnosticos` | Criar, listar e obter código e descrição | Admin, médico e enfermagem | Admin e médico |
| `/evolucoes` | Criar, listar e obter dados subjetivos, objetivos, avaliação e plano | Admin, médico e enfermagem | Admin, médico e enfermagem |
| `/administracoes` | Registrar, listar e obter administração ligada à prescrição e lote | Admin, médico e enfermagem | Admin, médico e enfermagem |

Use POST em `/consultas/{id}/cancelar`, `/consultas/{id}/concluir` e `/internacoes/{id}/alta`; use PUT em `/exames/{id}/resultado` com `{"resultado":"..."}`. A atualização de paciente, profissional ou leito substitui todos os campos do respectivo cadastro.

### Agenda e busca

O administrador cadastra janelas absolutas de disponibilidade em `POST /disponibilidades`, com `profissional_id`, `inicio` e `fim`; `GET /disponibilidades` permite filtrar por profissional. A exclusão de uma janela com consulta agendada é bloqueada. Antes de marcar uma consulta, cadastre uma janela que cubra todo seu período. A consulta aceita `duracao_minutos` entre 1 e 480 (padrão 30); horários sobrepostos do mesmo profissional são recusados. Cancelar libera o horário; concluir mantém o horário reservado no histórico.

Datas e horários dos eventos clínicos exigem fuso horário, por exemplo `2026-01-01T10:00:00-03:00`, e são normalizados para UTC. Campos que representam apenas uma data, como nascimento e validade, usam `AAAA-MM-DD`. Uma internação ativa ocupa um único leito e impede outra internação ativa do mesmo paciente; a alta libera ambos. Referências inexistentes retornam 404, conflitos retornam 409 e entradas inválidas retornam 422.

Em `GET /pacientes` e `GET /profissionais`, `q` busca por nome ou documento/registro. `GET /leitos?disponivel=true` lista leitos livres. Consultas aceitam `paciente_id`, `desde` e `ate`; os demais registros clínicos aceitam `paciente_id`. `GET /pacientes/{id}/historico` reúne consultas, internações, prontuários, prescrições, exames, alergias, diagnósticos, evoluções e administrações; `offset` e `limit` são aplicados separadamente a cada lista. O histórico é restrito ao administrador e aos profissionais vinculados.

### Registros e administração de medicamentos

Uma prescrição pode informar `medicamento_id`; quando informado, o nome deve corresponder ao medicamento cadastrado. Prescrições antigas, sem esse vínculo, são preservadas, mas não podem ser usadas para registrar administração com baixa de estoque; crie uma nova prescrição vinculada quando necessário.

`POST /administracoes` exige prescrição vinculada, profissional, lote, horário com fuso, quantidade inteira, dose e via informadas pelo usuário e uma chave UUID de `idempotencia`. A API verifica o vínculo com o paciente, o profissional responsável, o medicamento do lote, a validade e o saldo; grava a administração, a saída do lote e a auditoria na mesma transação. Repetir a mesma chave e os mesmos dados pelo mesmo usuário retorna o registro existente com 200, sem nova baixa; usar a chave com dados diferentes retorna 409. Registros podem ser consultados em `/administracoes` e no histórico.

Esses campos são apenas demonstração: a API **não calcula doses, verifica alergias ou contraindicações, valida a prescrição clinicamente nem garante que um medicamento foi administrado**. Não use esses fluxos para atendimento real.

### Auditoria

Leituras e alterações de pacientes, consultas, internações, prontuários, prescrições, exames, alergias, diagnósticos, evoluções e administrações geram eventos com usuário, ação, recurso, ID e horário, sem armazenar conteúdo clínico no evento. Os novos cadastros, autorizações, guias e tentativas de convênio também são auditados, sem número de carteirinha no evento. Eventos de vinculação e disponibilidade também são registrados. O administrador consulta `GET /auditoria`, com filtros opcionais `recurso` e `registro_id`. A criação ou alteração clínica e seu evento são gravados na mesma transação; leituras só são retornadas após o registro dos eventos.

Respostas 401, 403 e bloqueios 429 geram eventos em `GET /eventos-seguranca`, acessível ao administrador. Alterações de restrições registram o administrador, o usuário afetado e o nome da operação ou recurso. Os eventos não guardam senhas, tokens, corpo, caminho parametrizado ou parâmetros de busca. A redefinição local registra o usuário afetado, sem identificar o operador do sistema operacional. Se o evento de negação não puder ser gravado, a falha é propagada. Esses registros ficam no mesmo banco, não são invioláveis nem incluem versões anteriores do conteúdo, e não há política automática de retenção.

A aplicação não emite parâmetros SQL, envia `Cache-Control: no-store` e o comando recomendado desativa o log de acesso do Uvicorn. Configure também proxies, coletores e servidores externos para não registrar credenciais, corpos ou parâmetros sensíveis; restrinja o acesso ao banco e aos logs. Não coloque dados sensíveis em URLs. Não ative `DEBUG` em ambientes compartilhados.

### Estoque e faturamento

- `/medicamentos` cadastra medicamentos e um `estoque_minimo` configurável por `PUT /medicamentos/{id}/estoque-minimo`. Admin cadastra; admin/enfermagem movimentam; admin, médico e enfermagem consultam.
- Cadastre `/estoque/lotes` com medicamento, código e validade. Em `/estoque/movimentacoes`, informe `medicamento_id`, `lote_id`, quantidade e tipo `entrada`, `saida` ou `descarte`. Saídas não são permitidas em lotes vencidos; descarte permite retirar esses itens. Validades são consideradas até o fim do dia em UTC. O saldo total não pode ficar negativo.
- O saldo anterior à migração fica em `quantidade_nao_rastreada` e não está disponível para saída. Após identificar o lote e a validade, transfira unidades com `POST /estoque/regularizacoes` (`lote_id` e `quantidade`), sem alterar o saldo total. Movimentações anteriores continuam sem lote.
- `GET /estoque/alertas` lista medicamentos cujo saldo disponível está em ou abaixo do mínimo. Considera apenas lotes não vencidos; exclui quantidades não rastreadas e vencidas. `GET /estoque/lotes?vencido=true` lista lotes vencidos.
- `/convenios` cadastra e consulta convênios. `/cobrancas` cria e consulta cobranças de pacientes, com convênio opcional. `/cobrancas/{id}/pagamentos` registra e lista pagamentos manuais, inclusive parciais, sem permitir pagamento acima do saldo. Administração e recepção acessam cobranças e pagamentos; somente admin cadastra convênios. Valores são armazenados em centavos.

Esses módulos não processam pagamentos reais nem implementam dispensação clínica ou glosas reais. Não use prescrições ou resultados gerados aqui para atendimento real.

### Convênios e operadora simulada

O fluxo abaixo é **inteiramente local**, sem chamadas externas ou envio de dados a operadoras. Os códigos e resultados são fictícios; não implementam TISS, FHIR, carências, coparticipação, tabela contratual, glosa ou liquidação. A aceitação de uma guia não registra pagamento nem altera o saldo da cobrança. A cobrança anterior possui uma descrição livre, não um vínculo verificável com o procedimento: o sistema não comprova que o valor ou a descrição correspondem à autorização. Use apenas dados fictícios.

Admin cadastra planos, procedimentos e coberturas; admin e recepção consultam esses catálogos e gerenciam carteirinhas, autorizações e guias. Cada listagem aceita `offset` e `limit`, e carteirinhas, autorizações e guias aceitam o filtro `paciente_id`. No `/docs`, por exemplo:

1. Crie um convênio em `POST /convenios` com `{"nome":"Operadora ficticia"}` e um paciente em `/pacientes`.
2. Crie `POST /planos` com `{"convenio_id":1,"nome":"Plano ficticio"}`, `POST /procedimentos` com `{"codigo":"P-1","descricao":"Procedimento ficticio"}` e `POST /coberturas` com `{"plano_id":1,"procedimento_id":1}`.
3. Crie `POST /carteirinhas` com `{"paciente_id":1,"plano_id":1,"numero":"FICTICIO-1","inicio":"2026-01-01","fim":"2099-12-31"}`, substituindo os IDs e datas. O número deve ser único dentro do plano. A vigência é inclusiva, por data UTC.
4. Solicite `POST /autorizacoes-convenio` com `{"carteirinha_id":1,"procedimento_id":1,"idempotencia":"<uuid>"}`. O resultado é `aprovada` ou `negada`, com o motivo `aprovada`, `plano_inativo`, `carteirinha_inativa`, `fora_vigencia` ou `sem_cobertura`. Plano, carteirinha e cobertura devem estar ativos na data da solicitação. O resultado e a data de referência ficam registrados; alterações posteriores não mudam a autorização histórica.
5. Crie uma cobrança em `/cobrancas` para o mesmo paciente e convênio. Crie `POST /guias-convenio` com `{"autorizacao_id":1,"cobranca_id":1}` usando uma autorização aprovada. Cada autorização e cobrança só podem ser usadas em uma guia; duplicações retornam 409.
6. Envie `POST /guias-convenio/{id}/enviar` com `{"idempotencia":"<outro-uuid>"}`. O simulador reavalia a situação atual do plano, carteirinha e cobertura: a guia passa de `rascunho` para `aceita` ou `rejeitada`. Uma rejeitada pode ser reenviada com nova chave após correção; uma aceita não pode ser enviada novamente com outra chave. Consulte os resultados em `GET /guias-convenio/{id}/tentativas`.

Gere cada UUID, por exemplo, com `[guid]::NewGuid()` no PowerShell. Repetir uma solicitação de autorização ou envio com a mesma chave, dados e usuário retorna o resultado original com 200, inclusive quando houve rejeição; reutilizar a chave com outros dados ou usuário retorna 409. Para reavaliar, use uma chave nova. Chaves de autorização e envio são independentes.

Para mudanças, use `PUT /planos/{id}/status` com `{"ativo":false}`, `PUT /coberturas/{id}` com `{"ativa":false}` ou `PUT /carteirinhas/{id}` com `inicio`, `fim` e `ativa`; use `true` para reativar. O vínculo da carteirinha com paciente e plano não é alterado por essas operações. A avaliação e as alterações relevantes do mesmo plano são serializadas no banco.

## Monitoramento e backup SQLite

`GET /health` verifica se a API responde; `GET /health/ready` retorna 503 se o banco estiver indisponível ou não estiver na revisão mais recente. Um administrador pode consultar `GET /monitoramento` para contagens de acessos negados e bloqueios de login nas últimas 24 horas e medicamentos com estoque baixo. Um monitor externo deve consultar essas rotas e gerar alertas; não há envio automático de alertas.

SQLite é adequado para esta demonstração local, mas permite apenas um escritor por vez. `SQLITE_BUSY_TIMEOUT_MS` determina quanto uma conexão aguarda por bloqueios. Para um banco em arquivo, `SQLITE_WAL=true` habilita WAL nas conexões da aplicação; a ativação falha explicitamente se o banco não o suportar. WAL não elimina o limite de um escritor, não é adequado para sistemas de arquivos de rede comuns e exige persistir e proteger também os arquivos `-wal` e `-shm`. Em implantação, use armazenamento persistente local e mantenha banco, arquivos auxiliares e backups protegidos. Os testes cobrem disputas de estoque e agendamento, mas não representam uma avaliação de carga de produção.

Para SQLite em arquivo, faça uma cópia consistente do banco configurado e teste a restauração para **um arquivo novo**:

```powershell
python backup_sqlite.py backup --destino .\backup-hospital.db
python backup_sqlite.py restaurar --origem .\backup-hospital.db --destino .\restaurado-hospital.db
```

O utilitário valida a integridade e exige uma revisão Alembic, mas não sobrescreve destinos existentes nem troca o banco ativo. Para usar uma cópia restaurada, pare a aplicação, valide-a e configure `DATABASE_URL` para o arquivo escolhido. Após uma restauração, rotacione `SECRET_KEY`: uma cópia antiga pode conter versões de revogação anteriores e permitir novamente tokens ainda válidos. O utilitário não aceita bancos em memória, URLs SQLite com parâmetros ou outros bancos.

Backups não são criptografados nem agendados. Guarde-os fora do repositório, com permissões de acesso apropriadas e proteção em repouso, e teste periodicamente sua recuperação. Proteja também os arquivos auxiliares SQLite (`-wal` e `-shm`).

## Banco e evolução

Os modelos estão em `models/` e a migração inicial em `migrations/versions/`. Após alterar modelos, gere uma nova revisão com `python -m alembic revision --autogenerate -m "descricao"`, revise o arquivo gerado e aplique-a com `python -m alembic upgrade head`. Não altere migrações já aplicadas em outros ambientes.

A migração incremental preserva os registros antigos, define duração de 30 minutos para consultas anteriores e deixa o profissional de internações antigas vazio. Não cria vínculos retroativos nem janelas: o administrador deve configurá-los antes de liberar o acesso clínico e novos agendamentos. Consultas antigas mantêm seus horários, inclusive possíveis sobreposições anteriores à nova regra. Um downgrade remove as tabelas e dados adicionados pela evolução; faça backup antes de executá-lo.

A migração de segurança e estoque mantém saldos e movimentações existentes, identifica o saldo antigo como não rastreado e não cria lotes fictícios. Ela invalida tokens antigos e adiciona as novas tabelas; execute-a com a aplicação parada e após fazer backup. Seu downgrade remove vínculos com lotes, restrições e eventos de segurança; não o execute sem avaliar a perda de dados.

A migração clínica mantém prescrições anteriores com `medicamento_id` vazio e cria tabelas para os novos registros, restrições e limite de login. Seu downgrade remove esses dados; faça backup antes de atualizar ou reverter.

A migração de convênios adiciona novas tabelas sem modificar convênios e cobranças existentes. Faça backup e pare a aplicação antes de executar `python -m alembic upgrade head`; o downgrade remove planos, carteirinhas, coberturas, autorizações, guias e tentativas.

## Demonstração com dados fictícios

Depois de configurar `.env` e `SECRET_KEY`, crie um banco **novo**, separado do banco usado anteriormente. O comando recusa um destino existente e solicita uma senha; se a criação falhar após reservar o arquivo, examine e remova manualmente esse arquivo antes de tentar novamente.

```powershell
python demonstracao.py --database .\demo.db
$env:DATABASE_URL = "sqlite:///./demo.db"
uvicorn main:app --reload --no-access-log --no-proxy-headers
```

O banco contém o usuário `demo-admin`, um paciente, um profissional, uma janela de agenda e um medicamento com lote e estoque, todos fictícios. Em `/docs`:

1. Faça `POST /auth/login` com `demo-admin` e a senha escolhida; use o token no botão **Authorize**.
2. Consulte `/pacientes`, `/profissionais`, `/disponibilidades`, `/medicamentos` e `/estoque/lotes` para obter IDs e a data da janela.
3. Crie uma consulta na janela e registre uma alergia ou evolução fictícia para o paciente.
4. Crie uma prescrição com o ID e o nome do medicamento fictício. Registre uma administração com o ID da prescrição, o lote, o profissional, uma quantidade e um UUID novo, por exemplo gerado no PowerShell com `[guid]::NewGuid()`.
5. Consulte `/pacientes/{id}/historico`, `/estoque/movimentacoes` e `/auditoria`. Repita a administração com a mesma chave e os mesmos dados: o saldo não será baixado novamente.

Por exemplo, para `POST /consultas`, use o `inicio` retornado por `GET /disponibilidades` como `data_hora`. Substitua também os IDs pelos valores consultados:

```json
{
  "paciente_id": 1,
  "profissional_id": 1,
  "data_hora": "<inicio-da-disponibilidade-com-fuso>",
  "motivo": "Consulta ficticia",
  "duracao_minutos": 30
}
```

Para `POST /prescricoes`, substitua a data e os IDs da mesma forma:

```json
{
  "paciente_id": 1,
  "profissional_id": 1,
  "data_hora": "<inicio-da-disponibilidade-com-fuso>",
  "medicamento": "Medicamento ficticio",
  "medicamento_id": 1,
  "orientacoes": "Informacao ficticia"
}
```

Use o `id` da resposta da prescrição em `POST /administracoes`, substituindo também os demais IDs, a data e o UUID:

```json
{
  "prescricao_id": 1,
  "profissional_id": 1,
  "lote_id": 1,
  "idempotencia": "<uuid-novo>",
  "data_hora": "<data-e-hora-com-fuso>",
  "quantidade": 1,
  "dose": "Informacao ficticia",
  "via": "Informacao ficticia"
}
```

Os schemas e exemplos das demais requisições estão em `/docs`. Não coloque pacientes, informações clínicas ou credenciais reais nesse banco de demonstração.

A variável `DATABASE_URL` definida no PowerShell também afeta outros comandos executados **nesse terminal**. Para voltar a usar a URL do `.env`, pare a API e execute `Remove-Item Env:\DATABASE_URL`; isso não apaga nenhum banco. Em Linux ou macOS, use `export DATABASE_URL="sqlite:///./demo.db"` para selecionar a demonstração e `unset DATABASE_URL` para voltar à configuração do `.env`.

## Testes e qualidade

Com as dependências de `requirements-dev.txt` instaladas e o ambiente virtual ativo:

```powershell
python -m pytest -q
python -m ruff check .
```

O primeiro comando executa os testes automatizados; o segundo verifica o código com Ruff. Os testes usam bancos temporários e não exigem que o servidor esteja em execução. O workflow de CI está configurado para executar essas verificações com Python 3.12 e 3.14.

## Estrutura do projeto

```text
.
├── core/                 Configuração, tokens e senhas
├── database/             Conexão e sessões do banco
├── dependencies/         Autenticação e permissões
├── migrations/           Migrações do Alembic
├── models/               Tabelas e relacionamentos
├── routes/               Endpoints da API
├── schemas/              Validação e formatos de entrada e saída
├── services/             Regras compartilhadas e operadora simulada
├── tests/                Testes automatizados
├── main.py               Aplicação FastAPI
├── criar_admin.py        Criação local do administrador
├── demonstracao.py       Criação de um banco fictício separado
├── backup_sqlite.py      Backup e restauração SQLite
├── requirements.txt      Dependências da API
└── requirements-dev.txt  Dependências da API e ferramentas de desenvolvimento
```

## Dúvidas frequentes

**O PowerShell bloqueou a ativação do ambiente virtual.** Como alternativa, sem ativá-lo, use `.\.venv\Scripts\python.exe` no lugar de `python` em cada comando. Por exemplo: `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`. Para iniciar o servidor, use o mesmo executável com `-m uvicorn` e os argumentos da seção de instalação.

**A API informa que `SECRET_KEY` está ausente ou é curta.** Confira se o `.env` está na pasta do projeto, se a chave tem pelo menos 32 caracteres e se você executou o comando nessa pasta. Variáveis de ambiente com o mesmo nome têm precedência sobre o `.env`.

**A resposta é 401 ou 403.** Verifique o login e o token, faça login novamente se necessário e confira o perfil, os vínculos e as restrições do usuário. Algumas requisições sem credenciais também podem retornar 403.

**A resposta é 404, 409 ou 422.** `404` indica que um registro ou rota não foi encontrado; `409`, um conflito com dados ou regras existentes; `422`, campos ou formatos inválidos. Consulte o campo `detail` da resposta e os campos da operação em `/docs`.

**O login retorna 429.** Muitas tentativas inválidas podem bloquear temporariamente o endereço. Aguarde o prazo informado no cabeçalho `Retry-After`; o limite é explicado em [autenticação](#autenticação-e-permissões).

**`/health/ready` retorna 503.** Confira se o banco configurado está acessível e se as migrações estão atualizadas. Para um banco existente, faça backup antes de executar `python -m alembic upgrade head`.

**O comando de administrador informa que o login já existe.** Use a conta existente ou escolha outro login. Para redefinir a senha de uma conta existente, use o procedimento local descrito em [autenticação](#autenticação-e-permissões).

## Licença

Distribuído sob a [licença MIT](LICENSE). Consulte o arquivo para os termos completos.
