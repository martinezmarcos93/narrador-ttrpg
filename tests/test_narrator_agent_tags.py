

def test_strip_removes_echoed_context_and_spanish_state_tags():
    from narrator.agents.narrator_agent import NarratorAgent

    raw = ("[STATE | Estado mutable de la campaña | fuente: StateManager]\n"
           "Sistema: vtm_v20\nCampaña: Noches de Ceniza\n\n"
           "[estado: sangre delta -1] Lucía avanza por el pasillo.")
    agent = NarratorAgent()
    clean = agent.strip_system_tags(raw)
    assert clean == "Lucía avanza por el pasillo."
    assert agent.strip_context_echo(raw)[1] is True
