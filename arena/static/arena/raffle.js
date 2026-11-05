(() => {
    const el = id => document.getElementById('raffle-' + id);
    let state = null, busy = false;
    const storageKey = 'senac-raffle-pending';
    let pending = localStorage.getItem(storageKey);
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    function message(text, error = false) {
        ['message', 'import-message'].forEach(id => {
            el(id).textContent = text;
            el(id).style.color = error ? '#b91c1c' : '#002d72';
        });
    }
    function controls() {
        el('draw').disabled = busy || !state || (!pending && !state.remaining);
        el('file').disabled = busy || Boolean(pending);
        el('refresh').disabled = busy;
        el('reset').disabled = busy || !state || (!pending && !state.winners.length);
        el('draw').textContent = busy ? '✦ Sorteando…' : pending ? 'Recuperar sorteio pendente' : '✦ Sortear agora';
    }
    function showWinner(winner) {
        el('stage').classList.remove('raffle-rolling', 'raffle-revealed');
        el('eyebrow').textContent = 'A estrela da vez é…';
        el('name').textContent = winner.name;
        el('unit').textContent = winner.unit;
        void el('stage').offsetWidth;
        el('stage').classList.add('raffle-revealed');
    }
    function render() {
        el('total').textContent = state.total;
        el('remaining').textContent = state.remaining;
        el('count').textContent = state.winners.length;
        el('history').replaceChildren();
        if (!state.winners.length) {
            const item = document.createElement('li');
            item.textContent = 'Seu primeiro sorteado vai aparecer aqui. Boa sorte!';
            el('history').append(item);
        }
        state.winners.forEach((winner, index) => {
            const item = document.createElement('li');
            const place = document.createElement('span');
            place.className = 'raffle-place';
            place.textContent = '#' + (state.winners.length - index);
            const detail = document.createElement('div');
            const name = document.createElement('strong');
            name.textContent = winner.name;
            const unit = document.createElement('p');
            unit.textContent = winner.unit;
            const time = document.createElement('time');
            time.dateTime = winner.drawn_at;
            time.textContent = new Date(winner.drawn_at).toLocaleString('pt-BR', {timeZone: 'America/Sao_Paulo'});
            detail.append(name, unit, time);
            item.append(place, detail);
            el('history').append(item);
        });
        el('stage-note').textContent = state.remaining
            ? state.remaining + ' pessoas na disputa · sem repetir sorteados'
            : state.total ? 'Todos os participantes aptos já foram sorteados.' : 'Importe uma planilha para abrir os sorteios.';
        controls();
    }
    async function load() {
        state = await apiFetch('/raffle/');
        render();
    }
    el('refresh').addEventListener('click', async () => {
        busy = true; controls();
        try { await load(); message('Dados atualizados.'); }
        catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    });
    el('reset').addEventListener('click', async () => {
        if (busy || !window.confirm('Resetar todos os sorteios? O histórico de sorteados será apagado e todos os participantes da lista ativa poderão ganhar novamente.')) return;
        busy = true; controls(); message('Reiniciando os sorteios…');
        try {
            const result = await apiFetch('/raffle/reset/', {method: 'POST'});
            localStorage.removeItem(storageKey); pending = null;
            el('stage').classList.remove('raffle-rolling', 'raffle-revealed');
            el('eyebrow').textContent = 'O palco está pronto';
            el('name').textContent = 'Quem vai brilhar agora?';
            el('unit').textContent = 'Sorteios reiniciados. Boa sorte!';
            await load();
            message(result.detail);
        } catch (error) { message(error.message, true); }
        finally { busy = false; controls(); }
    });
    el('file').addEventListener('change', async event => {
        const file = event.target.files[0];
        if (!file) return;
        busy = true; controls(); message('Conferindo participantes e salvando a lista…');
        try {
            const data = new FormData();
            data.append('file', file);
            const response = await fetch('/api/raffle/import/', {
                method: 'POST', headers: {'X-CSRFToken': CSRF_TOKEN}, body: data
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || 'Não foi possível importar.');
            message(result.imported + ' aptos salvos · ' + result.excluded + ' excluídos · ' + result.duplicates + ' duplicados ignorados. Histórico preservado.');
            await load();
            if (!state.winners.length) {
                el('name').textContent = 'Quem vai brilhar agora?';
                el('unit').textContent = 'Sua lista está pronta. Boa sorte!';
            }
        } catch (error) { message(error.message, true); }
        finally { busy = false; event.target.value = ''; controls(); }
    });
    el('draw').addEventListener('click', async () => {
        if (busy) return;
        busy = true; controls(); message('Preparando a revelação…');
        let timer;
        try {
            if (!pending) {
                pending = typeof crypto.randomUUID === 'function' ? crypto.randomUUID()
                    : '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, digit =>
                        (digit ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> digit / 4).toString(16));
                localStorage.setItem(storageKey, pending);
            }
            el('stage').classList.remove('raffle-revealed');
            el('stage').classList.add('raffle-rolling');
            el('eyebrow').textContent = 'A sorte está em movimento';
            el('result').setAttribute('aria-live', 'off');
            if (!reduced && state.participants.length) {
                let frame = 0;
                timer = setInterval(() => {
                    const person = state.participants[frame++ % state.participants.length];
                    el('name').textContent = person.name;
                    el('unit').textContent = person.unit;
                }, 95);
            }
            // O banco confirma o resultado antes da animação de revelação.
            const response = await fetch('/api/raffle/draw/', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN},
                body: JSON.stringify({request_id: pending})
            });
            const winner = await response.json();
            if (!response.ok) {
                if (response.status === 400 || response.status === 409) {
                    localStorage.removeItem(storageKey); pending = null;
                    try { await load(); } catch (_) {}
                }
                throw new Error(winner.detail || 'Não foi possível confirmar o sorteio.');
            }
            localStorage.removeItem(storageKey); pending = null;
            if (!reduced) await new Promise(resolve => setTimeout(resolve, 3200));
            clearInterval(timer);
            el('result').setAttribute('aria-live', 'polite');
            showWinner(winner);
            if (!reduced && typeof confetti === 'function') {
                confetti({particleCount: 160, spread: 100, origin: {y: .65}, colors: ['#f37021', '#ffb800', '#00d2ff', '#ffffff']});
            }
            playAudioEffect('victory');
            message('Resultado salvo! ' + winner.name + ' não participará dos próximos sorteios.');
            try { await load(); }
            catch (error) { message('Resultado salvo. Atualize para sincronizar o histórico.', true); }
        } catch (error) {
            clearInterval(timer);
            el('stage').classList.remove('raffle-rolling');
            el('result').setAttribute('aria-live', 'polite');
            el('name').textContent = 'Vamos conferir o resultado';
            el('unit').textContent = pending ? 'Clique em recuperar para consultar o mesmo sorteio.' : 'Atualize os participantes para continuar.';
            message(error.message, true);
        } finally { clearInterval(timer); busy = false; controls(); }
    });
    document.addEventListener('DOMContentLoaded', async () => {
        try {
            await load();
            if (state.winners.length) showWinner(state.winners[0]);
            else if (state.remaining) el('unit').textContent = 'Sua lista está salva. Boa sorte!';
            if (pending) message('Há um sorteio pendente. Recupere o resultado antes de continuar.');
        } catch (error) { message('Não foi possível carregar os sorteios: ' + error.message, true); }
    });
})();
