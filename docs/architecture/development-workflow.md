# **Development Workflow**

## **Local Development Setup**

```bash
# Prerequisites
Python 3.9+
Windows 10+
8GB RAM minimum

# Setup
git clone <repository>
cd voice-ai-platform
pip install -r requirements.txt
cp config.example.json config.json
# Edit config.json with credentials

# Run
python src/main.py

# Access
http://localhost:8000/dashboard
```

## **Testing Strategy (MVP)**

```python
# Basic tests only for MVP
def test_emr_connectivity():
    """Verify EMR connection"""
    assert emr.test_connection() == True

def test_voice_pipeline():
    """Test voice processing"""
    result = voice.process_test_audio()
    assert result['status'] == 'success'

def test_appointment_creation():
    """Test appointment booking"""
    appointment = create_test_appointment()
    assert appointment.id is not None
```
