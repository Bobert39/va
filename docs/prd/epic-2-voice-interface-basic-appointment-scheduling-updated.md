# Epic 2: Voice Interface & Basic Appointment Scheduling (Updated)

**Expanded Goal:** Build upon PROVEN EMR integration to implement core voice-powered appointment scheduling. **Cannot begin until Epic 1 validates appointment creation APIs.**

## Story 2.1: Speech-to-Text Voice Processing (Updated)
As a **patient calling after hours**,
I want **the system to accurately understand my spoken words**,
so that **I can communicate my appointment needs naturally**.

### Acceptance Criteria (Updated)
1. Real-time speech-to-text transcription with ≥85% accuracy on test phrases (reduced from 90% based on assumption testing)
2. Support for common speech patterns, accents, and speaking speeds
3. Audio input handling from standard phone system integration
4. **VALIDATION ADDED**: Testing with practice-representative phone audio quality
5. **VALIDATION ADDED**: Cost modeling to ensure API usage stays within $197/month target
6. Conversation timeout handling after 30 seconds of silence
7. Clear audio feedback when system cannot understand input

## Story 2.2: Natural Language Appointment Request Processing (Updated)
As a **patient**,
I want **to describe my appointment needs in natural language**,
so that **I don't have to use specific commands or technical phrases**.

### Acceptance Criteria (Updated)
1. Extract patient name, preferred date/time, and appointment reason from natural speech
2. Handle various date formats ("tomorrow", "next Tuesday", "January 15th")
3. Understand appointment types ("checkup", "follow-up", "urgent", "consultation")
4. **VALIDATION ADDED**: Test with medical terminology and healthcare-specific language
5. **COST CONTROL**: Optimize API calls to minimize OpenAI usage costs
6. Confirmation of understood details before proceeding
7. Context retention throughout multi-turn conversation

## Story 2.3: Appointment Conflict Detection and Resolution
As a **practice**,
I want **the system to prevent double-booking and scheduling conflicts**,
so that **provider schedules remain accurate and manageable**.

### Acceptance Criteria
1. Real-time checking of provider availability before confirming appointments
2. Detection of existing appointments in requested time slots
3. Alternative time suggestions when preferred slots unavailable
4. Buffer time consideration between appointments (15-30 minutes)
5. Provider-specific scheduling rules and preferences
6. Holiday and break time conflict prevention
7. Zero double-booking rate in testing scenarios

## Story 2.4: EMR Appointment Creation Integration
As a **practice staff member**,
I want **voice-scheduled appointments to appear immediately in OpenEMR**,
so that **providers see complete schedules without manual entry**.

### Acceptance Criteria
1. Create new appointment records via OpenEMR appointment API
2. Link appointments to existing patient records from lookup
3. Include appointment type, duration, reason, and notes
4. Handle API failures with retry logic and error recovery
5. Appointment confirmation numbers generated and communicated
6. All appointment data synchronized immediately with EMR
7. Audit trail of all appointment creation attempts and results

## Story 2.5: Voice Confirmation and Interaction Flow
As a **patient**,
I want **clear voice confirmation of my appointment details**,
so that **I'm confident my appointment is correctly scheduled**.

### Acceptance Criteria
1. Text-to-speech confirmation including date, time, provider, location
2. Clear pronunciation of medical terms and practice-specific information
3. Option for patient to confirm or request changes to appointment
4. Professional, friendly tone consistent with practice communication style
5. Conversation completion within 3-5 voice exchanges maximum
6. Graceful handling when patient needs to hang up mid-conversation
7. Integration with Azure Speech Services or equivalent TTS provider

## Story 2.6: Error Recovery and Human Handoff (Updated)
As a **patient experiencing difficulties**,
I want **clear options to reach a human when the voice system cannot help**,
so that **I can still schedule my appointment successfully**.

### Acceptance Criteria (Updated)
1. "Speak to someone" and similar phrases trigger human handoff
2. Automatic handoff when voice recognition confidence drops below 70%
3. **PATIENT ACCEPTANCE**: Clear disclosure that patient is speaking with AI system
4. **DEMOGRAPHIC TESTING**: Validate handoff options work for elderly and non-English speaking patients
5. System saves partial appointment information for staff follow-up
6. Error logging for continuous improvement of voice recognition
7. Practice-configurable handoff phone numbers and procedures
