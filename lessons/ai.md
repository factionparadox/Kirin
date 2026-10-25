# Study with the local coding model

Kirin keeps the existing openKylin AI stack and adds Qwen2.5-Coder 7B Instruct for coding lessons. The offline Kirin Learn lessons do **not** require either model.

Once Ollama and the image-supplied coding model are installed:

    kirin-learn ask-code 'Explain what apt-cache policy shows'

Only that explicit question is sent to the **local loopback Ollama API**, not to a cloud endpoint. The assistant neither runs its generated code nor automatically reads your files.

**Exercise:** Ask Qwen about `apt update` and compare its response to `kirin-learn explain 'apt update'` and `man apt`.

## Use Kirin's models in the Kirin AI Assistant

Kirin normally replaces openKylin's assistant ("Xiao K") with **Alpaca**, which is already connected. If your build kept the assistant, it can use Kirin's models too; it does not find Ollama by itself, so add it once as a custom model:

1. Open **Settings → AI** (model configuration) and choose to add a **custom / private model** ("deployed on the enterprise intranet or local server").
2. Fill in:
   * Address: `http://127.0.0.1:11434/v1` (if it asks for the full endpoint: `http://127.0.0.1:11434/v1/chat/completions`)
   * API key: `ollama` (any text; Ollama ignores it, but the form may require one)
   * Model name: `qwen3:30b-a3b-instruct-2507-q4_K_M` for general chat and Russian, or `qwen2.5-coder:7b-instruct` for code
3. Save, then set the custom model first in the priority order.

Everything stays on this computer: Ollama listens only on 127.0.0.1. The **Alpaca** app is already connected and needs no setup.

Check what is installed with `ollama list`, and that the service is running with `systemctl status ollama`.
