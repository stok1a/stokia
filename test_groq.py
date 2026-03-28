from groq import Groq

cliente = Groq(api_key="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")

respuesta = cliente.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "user", "content": "Hola, responde solo: StokIA conectado correctamente"}
    ]
)

print(respuesta.choices[0].message.content)
