import struct
import os
from pathlib import Path
from subprocess import CalledProcessError

import asyncio
import aiofiles
from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse


app = FastAPI()

ALLOWED_MIME_TYPE = ["model/stl", "application/sla", "application/octet-stream"]
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
PRUSA_SLICER_PATH = "/usr/bin/prusa-slicer"


def is_ascii_stl(file_content: bytes) -> bool:
    """Check if the file is ASCII STL by inspecting the start and end."""
    try:
        text_content = file_content.decode("utf-8")
        return text_content.startswith("solid") and text_content.strip().endswith(
            "endsolid"
        )
    except UnicodeDecodeError:
        return False


def is_binary_stl(file_content: bytes) -> bool:
    """Check if the file is Binary STL by inspecting the header and triangle count."""
    if len(file_content) < 84:  # Minimum binary STL size
        return False
    num_triangles = struct.unpack("<I", file_content[80:84])[0]
    expected_size = 84 + num_triangles * 50
    return len(file_content) == expected_size


def validate_stl(file_content: bytes) -> bool:
    """Validate if the file is either ASCII or Binary STL."""
    if is_ascii_stl(file_content):
        return True
    elif is_binary_stl(file_content):
        return True
    return False


@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile):
    if not file:
        return JSONResponse({"error": "No file uploaded"}, 400)

    if file.content_type not in ALLOWED_MIME_TYPE or not file.filename.endswith(".stl"):
        return JSONResponse({"error": "Not an STL file"}, 400)

    if file.size is None or file.size > 20 * 10e6:
        return JSONResponse({"error": "File size too large"}, 400)

    file_content = await file.read()

    if not validate_stl(file_content):
        return JSONResponse({"error": "File corrupted"})

    safe_filename = os.path.basename(file.filename)
    file_path = os.path.join(UPLOADS_DIR, safe_filename)

    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(file_content)

    gcode_file_path = os.path.join(UPLOADS_DIR, safe_filename.replace(".stl", ".gcode"))
    success, error_message = await run_prusa_slicer(
        str(file_path), str(gcode_file_path)
    )

    if not success:
        return JSONResponse({"error": "Calculation failed"}, 500)

    metadata = await parse_gcode_for_metadata(str(gcode_file_path))

    return {
        "filename": file.filename,
        "print_time": metadata["print_time"],
        "filament_used_cm3": metadata["filament_used_cm3"],
        "detail": "STL file processed and G-code generated.",
    }


async def run_prusa_slicer(
    stl_file_path: str, output_file_path: str, timeout: int = 15
):
    """Run PrusaSlicer on the uploaded file asynchronously with a timeout."""
    try:
        # Run PrusaSlicer as an async subprocess and wait for it to complete within 15 seconds
        process = await asyncio.create_subprocess_exec(
            PRUSA_SLICER_PATH,
            stl_file_path,
            "--export-gcode",
            "--output",
            output_file_path,
            "--load",
            "slicer.ini",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for the process to complete with a timeout
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

        if process.returncode != 0:
            raise CalledProcessError(
                process.returncode, PRUSA_SLICER_PATH, output=stdout, stderr=stderr
            )

        return True, ""

    except (asyncio.TimeoutError, CalledProcessError, Exception) as exc:
        print(exc)
        return False, "Couldnt generate gcode"


async def parse_gcode_for_metadata(gcode_file_path: str):
    """Parse the G-code file to extract print time and filament usage."""
    print_time = None
    filament_used = None

    async with aiofiles.open(gcode_file_path, "r") as gcode_file:
        async for line in gcode_file:
            if line.startswith("; estimated printing time (normal mode)"):
                # Extract print time in seconds
                print_time = line.strip().split("=")[1]
            elif line.startswith("; filament used [cm3] = "):
                # Extract filament usage in meters
                filament_used = float(line.strip().split("=")[1].strip())

    # Return print time in seconds and filament usage in meters
    return {"print_time": print_time, "filament_used_cm3": filament_used}


@app.get("/", response_class=HTMLResponse)
async def index():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>STL File Upload</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background-color: #f5f5f5;
                padding: 20px;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background-color: #fff;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
            }
            h1 {
                text-align: center;
                margin-bottom: 20px;
            }
            label {
                font-size: 16px;
                font-weight: bold;
            }
            input[type="file"] {
                display: block;
                margin: 10px 0;
            }
            button {
                padding: 10px 20px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }
            button:hover {
                background-color: #45a049;
            }
            .output {
                margin-top: 20px;
            }
            .output p {
                padding: 10px;
                border-radius: 5px;
            }
            .success {
                background-color: #d4edda;
                color: #155724;
            }
            .error {
                background-color: #f8d7da;
                color: #721c24;
            }
        </style>
    </head>
    <body>

    <div class="container">
        <h1>Upload STL File for Slicing</h1>
        
        <form id="uploadForm">
            <label for="stlFile">Select an STL file:</label>
            <input type="file" id="stlFile" name="stlFile" accept=".stl" required>
            <button type="submit">Upload and Process</button>
        </form>

        <div class="output" id="output"></div>
    </div>

    <script>
        const form = document.getElementById('uploadForm');
        const output = document.getElementById('output');

        form.addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent the form from submitting the traditional way

            const fileInput = document.getElementById('stlFile');
            const file = fileInput.files[0];

            if (!file) {
                displayMessage("Please select a file to upload", "error");
                return;
            }

            const formData = new FormData();
            formData.append("file", file);

            try {
                // Send file via POST request to FastAPI backend
                const response = await fetch("/uploadfile/", {
                    method: "POST",
                    body: formData,
                });

                const data = await response.json();

                if (response.ok) {
                    displayMessage(`
                        <strong>File:</strong> ${data.filename}<br>
                        <strong>Print Time: </strong> ${data.print_time}<br>
                        <strong>Filament Used (cm3):</strong> ${data.filament_used_cm3}
                    `, "success");
                } else {
                    displayMessage(data.error || "An error occurred while processing the file", "error");
                }
            } catch (err) {
                displayMessage("Failed to upload the file. Please try again.", "error");
            }
        });

        function displayMessage(message, type) {
            output.innerHTML = `<p class="${type}">${message}</p>`;
        }
    </script>

    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
