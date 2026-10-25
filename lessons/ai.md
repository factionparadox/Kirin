# Study with the local coding model

Kirin keeps the existing openKylin AI stack and adds Qwen2.5-Coder 7B Instruct for coding lessons. The offline Kirin Learn lessons do **not** require either model.

Once Ollama and the image-supplied coding model are installed:

    kirin-learn ask-code 'Explain what apt-cache policy shows'

Only that explicit question is sent to the **local loopback Ollama API**, not to a cloud endpoint. The assistant neither runs its generated code nor automatically reads your files.

**Exercise:** Ask Qwen about `apt update` and compare its response to `kirin-learn explain 'apt update'` and `man apt`.
