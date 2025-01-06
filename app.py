import os
import uuid
import base64
import shutil
import json

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env if present
load_dotenv()

# Setup log level based on DEBUG environment variable
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
if DEBUG:
    logger.info("Running in DEBUG mode")
else:
    logger.info("Running in PRODUCTION mode")

# Default temp directory
DEFAULT_TMPDIR = "/tmp/"
MARKITDOWN_TMPDIR = os.getenv("MARKITDOWN_TMPDIR", DEFAULT_TMPDIR)

from markitdown import MarkItDown
from openai import OpenAI # from the user's example

app = Flask(__name__)

@app.route("/", methods=["GET"])
def root():
    return "ok"

@app.route("/convert", methods=["POST"])
def convert_files():
    """
    API endpoint to convert files using MarkItDown.

    POST Body JSON Structure:
    {
        "llmConfig": {
            "openaiApiKey": "",
            "openaiBaseUrl": "",
            "llmModel": ""
        },
        "data": [
            {
                "fileName": "test.xlsx",
                "fileContent": "base64-string"
            }
        ]
    }
    """
    try:
        payload = request.get_json()
        if payload is None:
            logger.error("No JSON payload provided.")
            return jsonify({"error": "No JSON payload provided"}), 500

        llm_config = payload.get("llmConfig", None)
        data = payload.get("data", [])

        if not isinstance(data, list) or len(data) == 0:
            logger.error("No valid 'data' array provided.")
            return jsonify({"error": "No valid 'data' array provided"}), 500

        # Generate a unique folder under MARKITDOWN_TMPDIR
        unique_id = str(uuid.uuid4())
        working_dir = os.path.join(MARKITDOWN_TMPDIR, unique_id)
        logger.debug(f"Creating working directory: {working_dir}")
        os.makedirs(working_dir, exist_ok=True)
        logger.info(f"LLM Configuration: {llm_config}")

        # Decide whether to instantiate MarkItDown with or without LLM
        if llm_config and all(k in llm_config for k in ["openaiApiKey", "llmModel"]):
            logger.info("Using MarkItDown with LLM configuration.")
            openai_api_key = llm_config["openaiApiKey"]
            llm_model = llm_config["llmModel"]
            
            # Create OpenAI client with optional base_url
            client_kwargs = {"api_key": openai_api_key}
            if "openaiBaseUrl" in llm_config:
                client_kwargs["base_url"] = llm_config["openaiBaseUrl"]
                
            client = OpenAI(**client_kwargs)
            md = MarkItDown(llm_client=client, llm_model=llm_model)
        else:
            logger.info("Using MarkItDown without LLM configuration.")
            md = MarkItDown()

        results = []

        # Process each file in the data array
        for item in data:
            file_name = item.get("fileName")
            file_content_base64 = item.get("fileContent")

            if not file_name or not file_content_base64:
                logger.warning("Skipping invalid file entry due to missing fileName or fileContent.")
                return jsonify({"error": "Missing fileName or fileContent"}), 500

            # Decode normal Base64 content
            try:
                file_bytes = base64.b64decode(file_content_base64)
            except Exception as e:
                logger.error(f"Failed to decode base64 content for file: {file_name}. Error: {e}")
                return jsonify({"error": f"Failed to decode base64 for {file_name}: {e}"}), 500

            # Save the file to the working directory
            file_path = os.path.join(working_dir, file_name)
            logger.debug(f"Saving file to path: {file_path}")
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            try:
                # Convert file using MarkItDown
                logger.debug(f"Converting file: {file_path}")
                result = md.convert(file_path)
                conversion_output = result.text_content
            except Exception as e:
                logger.error(f"Conversion failed for file: {file_name}. Error: {e}")
                return jsonify({"error": f"Conversion failed for file: {file_name}. Error: {e}"}), 500

            # Append to results
            results.append({
                "fileName": file_name,
                "conversionResult": conversion_output
            })

        return jsonify(results), 200

    except Exception as e:
        logger.exception(f"Unhandled error: {e}")
        return jsonify({"error": str(e)}), 500

    finally:
        # Cleanup: remove working directory after processing
        if 'working_dir' in locals() and os.path.exists(working_dir):
            logger.debug(f"Removing working directory: {working_dir}")
            shutil.rmtree(working_dir, ignore_errors=True)


if __name__ == "__main__":
    # For local debug/testing
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8585)), debug=DEBUG)