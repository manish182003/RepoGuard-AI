
import asyncio

from groq import AsyncGroq

from app.core.config import settings


async def main():
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not configured")

    client = AsyncGroq(api_key=settings.groq_api_key)

    try:
        response = await client.models.list()

        print("Models available to your Groq API key:\n")

        for model in response.data:
            if getattr(model, "active", True):
                print(model.id)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
