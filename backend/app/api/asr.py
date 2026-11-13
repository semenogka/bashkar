import os, tempfile, uuid
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

os.environ.setdefault("HF_HOME", "D:/hf-cache")

router = APIRouter(prefix="/asr", tags=["asr"])

_model = None


def get_model():
    global _model
    if _model is None:
        import onnx_asr
        _model = onnx_asr.load_model("AigizK/GigaAM-Bashkir-CV25-ONNX")
    return _model


@router.post("")
async def transcribe(file: UploadFile = File(...)):
    # Сохраняем загруженный файл
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.close()

        # Конвертируем в int16 wav, если нужно
        import scipy.io.wavfile as wav
        import numpy as np
        try:
            sr, data = wav.read(tmp.name)
            if data.dtype != np.int16:
                if np.issubdtype(data.dtype, np.floating):
                    data = (data * 32767).astype(np.int16)
                else:
                    data = data.astype(np.int16)
                conv_path = tmp.name + "_int16.wav"
                wav.write(conv_path, sr, data)
                audio_path = conv_path
            else:
                audio_path = tmp.name
        except Exception:
            audio_path = tmp.name

        model = get_model()
        text = model.recognize(audio_path)
        return {"text": text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        try:
            os.unlink(tmp.name + "_int16.wav")
        except Exception:
            pass