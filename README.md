# Fogos.pt para Home Assistant

Integração do [Home Assistant](https://www.home-assistant.io/) com a [API Fogos.pt](https://fogos.pt/pt/api). Traz para o Home Assistant:

- **Ocorrências ativas**: incêndios rurais, urbanos e em transportes, outros incêndios, FMA e outras ocorrências.
- **Avisos meteorológicos do IPMA**: continente, Madeira e Açores.
- **Sismos** dos últimos 7 dias.

Filtra por **vários distritos, concelhos e freguesias** e dispara eventos para criar **notificações**.

*[English below](#english)*

## Requisitos

- Home Assistant 2025.12 ou mais recente.
- **Chave pessoal da API Fogos.pt** (`X-API-Key`). Pede-se em <https://fogos.pt/pt/api>. A chave é individual: não a partilhe.

## Instalação

### HACS (recomendado)

1. No HACS, abra o menu ⋮, escolha **Repositórios personalizados** e adicione `https://github.com/FogosPT/fogos-pt-homeassistant` com a categoria **Integração**.
2. Procure **Fogos.pt**, instale e reinicie o Home Assistant.

### Manual

Copie `custom_components/fogos_pt` para a pasta `config/custom_components/` do Home Assistant e reinicie.

## Configuração

Vá a **Definições → Dispositivos e serviços → Adicionar integração → Fogos.pt**. O assistente tem estes passos:

1. **Chave da API**: é validada logo neste passo.
2. **Distritos**: as ilhas aparecem como distritos, por exemplo "Ilha Da Madeira" ou "Ilha De São Miguel". Se deixar vazio, segue o país inteiro.
3. **Concelhos** (opcional): um distrito sem concelhos escolhidos é seguido por inteiro.
4. **Freguesias** (opcional): um concelho sem freguesias escolhidas é seguido por inteiro.
5. **Áreas de aviso IPMA**: vêm sugeridas a partir dos locais. A ilha da Madeira tem Costa Norte, Costa Sul e Regiões Montanhosas, e os Açores estão divididos em grupos.
6. **Filtros**:
   - tipos de ocorrência;
   - região dos sismos, ou "Não seguir sismos";
   - magnitude mínima;
   - distância máxima a casa;
   - opção para mostrar só os sismos cujo local mais próximo fica nos locais escolhidos.

Tudo o que configurou pode ser alterado mais tarde em **Configurar**. Pode adicionar a integração mais do que uma vez, por exemplo uma para casa e outra para uma segunda habitação.

## Entidades

| Entidade | Descrição |
|---|---|
| `sensor.…_incendios_ativos` | Número de incêndios. Atributo `incidents`: lista com local, estado, meios e link |
| `sensor.…_outras_ocorrencias_ativas` | FMA e outras ocorrências |
| `sensor.…_operacionais`, `…_meios_terrestres`, `…_meios_aereos` | Totais dos meios no terreno |
| `sensor.…_avisos_ipma` | Número de avisos ativos. Atributos `warnings` e `max_level` |
| `sensor.…_nivel_de_aviso_mais_alto` | `green`, `yellow`, `orange` ou `red` |
| `sensor.…_ultimo_sismo` | Magnitude do sismo mais recente. Atributos: local, hora, profundidade, distância |
| `binary_sensor.…_incendio_na_zona` | Ligado quando há pelo menos um incêndio |
| `binary_sensor.…_aviso_laranja_ou_vermelho` | Ligado quando há um aviso laranja ou vermelho |
| `geo_location.*` (fonte `fogos_pt`) | Uma entidade por ocorrência e por sismo. Aparecem no cartão **Mapa** e servem para automações de zona |

Os dados são atualizados a cada 60 s (ocorrências), 5 min (avisos) e 2 min (sismos).

## Notificações

### Blueprints

Importe os blueprints para receber notificações na app Home Assistant:

| Blueprint | Importar |
|---|---|
| Nova ocorrência (e mudanças de estado) | [![Importar](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FFogosPT%2Ffogos-pt-homeassistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ffogos_pt%2Fnovo_incidente.yaml) |
| Novo aviso IPMA | [![Importar](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FFogosPT%2Ffogos-pt-homeassistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ffogos_pt%2Fnovo_aviso.yaml) |
| Novo sismo | [![Importar](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FFogosPT%2Ffogos-pt-homeassistant%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ffogos_pt%2Fnovo_sismo.yaml) |

### Eventos

Para automações à medida, a integração dispara estes eventos. Nenhum deles é disparado no arranque, apenas quando algo muda.

| Evento | Quando | Dados |
|---|---|---|
| `fogos_pt_new_incident` | Aparece uma ocorrência nova | `id`, `kind`, `is_fire`, `natureza`, `status`, `district`, `concelho`, `freguesia`, `location`, `latitude`, `longitude`, `man`, `terrain`, `aerial`, `url`, `entry_id` |
| `fogos_pt_incident_status_changed` | Uma ocorrência muda de estado | Os mesmos de `fogos_pt_new_incident` + `previous_status` |
| `fogos_pt_incident_ended` | Uma ocorrência deixa de estar ativa | Os mesmos de `fogos_pt_new_incident` |
| `fogos_pt_new_warning` | Aparece um aviso novo ou o nível sobe | `area`, `area_name`, `type`, `level`, `text`, `start`, `end` |
| `fogos_pt_new_earthquake` | Aparece um sismo novo acima da magnitude mínima | `id`, `magnitude`, `time`, `depth`, `place`, `nearest`, `nearest_municipality`, `distance_km`, `felt` |

Exemplo:

```yaml
automation:
  - alias: Incêndio grande perto de casa
    triggers:
      - trigger: event
        event_type: fogos_pt_new_incident
        event_data:
          is_fire: true
    conditions:
      - "{{ trigger.event.data.man >= 50 }}"
    actions:
      - action: notify.notify
        data:
          title: "🔥 {{ trigger.event.data.concelho }}"
          message: "{{ trigger.event.data.location }} — {{ trigger.event.data.man }} operacionais"
```

## Desenvolvimento

```bash
pip install -r requirements_test.txt
python -m pytest
```

---

## English

Home Assistant integration for the [Fogos.pt API](https://fogos.pt/pt/api).

- **What it provides:**
  - active incidents (rural/urban/transport fires, other fires, adverse weather, other incidents);
  - IPMA weather warnings for mainland Portugal, Madeira and the Azores;
  - earthquakes from the last 7 days.
- **Filtering:** by several districts, municipalities and parishes.
- **Notifications:** events and blueprints you can use to send them.

To use it:

1. Get a personal API key (`X-API-Key`) at <https://fogos.pt/pt/api>.
2. Add this repository to HACS as a custom repository (category **Integration**) and install **Fogos.pt**.
3. Add the integration from **Settings → Devices & services** and pick your locations, warning areas and filters.

The entities, events and blueprints are described above.

## Licença / License

AGPL-3.0, the same license as [fogosapi](https://github.com/FogosPT/fogosapi). Os dados pertencem às respetivas fontes: ANEPC, IPMA e Fogos.pt.
