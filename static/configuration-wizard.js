// Configuration Wizard JavaScript
class ConfigurationWizard {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 4;
        this.wizardData = {
            practice: {},
            providers: [],
            hours: {},
            appointmentTypes: []
        };
        this.isVisible = false;
        this.progressKey = 'va_wizard_progress';

        this.init();
    }

    init() {
        this.createWizardHTML();
        this.attachEventListeners();
        this.loadSavedProgress();
    }

    createWizardHTML() {
        const wizardHTML = `
            <div id="configurationWizardOverlay" class="wizard-overlay">
                <div class="wizard-container">
                    <div class="wizard-header">
                        <h2><i class="fas fa-magic"></i> Practice Setup Wizard</h2>
                        <p class="mb-0">Let's get your practice configured step by step</p>
                    </div>

                    <div class="wizard-progress">
                        <ul class="progress-steps">
                            <li class="progress-step current" data-step="1">
                                <span class="step-circle">1</span>
                                <span class="step-label">Practice Info</span>
                            </li>
                            <li class="progress-step" data-step="2">
                                <span class="step-circle">2</span>
                                <span class="step-label">Providers</span>
                            </li>
                            <li class="progress-step" data-step="3">
                                <span class="step-circle">3</span>
                                <span class="step-label">Business Hours</span>
                            </li>
                            <li class="progress-step" data-step="4">
                                <span class="step-circle">4</span>
                                <span class="step-label">Appointment Types</span>
                            </li>
                        </ul>
                    </div>

                    <div class="wizard-content">
                        <!-- Step 1: Practice Information -->
                        <div class="wizard-step active" data-step="1">
                            <h3 class="step-title">Practice Information</h3>
                            <p class="step-description">Tell us about your practice so we can customize the voice AI experience for your patients.</p>

                            <form id="practiceInfoForm">
                                <div class="row">
                                    <div class="col-md-8 mb-3">
                                        <label for="practiceName" class="form-label">
                                            Practice Name *
                                            <span class="help-tooltip">
                                                <i class="fas fa-question-circle text-info"></i>
                                                <span class="tooltip-content">This is how your practice will be identified to patients during voice interactions. Use your official practice name.</span>
                                            </span>
                                        </label>
                                        <input type="text" class="form-control" id="practiceName" required
                                               placeholder="e.g., Smith Family Medical Center">
                                        <div class="form-help-text">This name will be used in voice greetings to patients</div>
                                    </div>
                                    <div class="col-md-4 mb-3">
                                        <label for="practicePhone" class="form-label">Main Phone *</label>
                                        <input type="tel" class="form-control" id="practicePhone" required
                                               placeholder="(555) 123-4567">
                                    </div>
                                </div>

                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label for="practiceAddress" class="form-label">Street Address *</label>
                                        <input type="text" class="form-control" id="practiceAddress" required
                                               placeholder="123 Main Street">
                                    </div>
                                    <div class="col-md-3 mb-3">
                                        <label for="practiceCity" class="form-label">City *</label>
                                        <input type="text" class="form-control" id="practiceCity" required
                                               placeholder="Springfield">
                                    </div>
                                    <div class="col-md-2 mb-3">
                                        <label for="practiceState" class="form-label">State *</label>
                                        <input type="text" class="form-control" id="practiceState" required
                                               placeholder="NY" maxlength="2">
                                    </div>
                                    <div class="col-md-1 mb-3">
                                        <label for="practiceZip" class="form-label">ZIP *</label>
                                        <input type="text" class="form-control" id="practiceZip" required
                                               placeholder="12345" maxlength="5">
                                    </div>
                                </div>

                                <div class="mb-3">
                                    <label for="practiceGreeting" class="form-label">
                                        Custom Greeting Message
                                        <span class="help-tooltip">
                                            <i class="fas fa-question-circle text-info"></i>
                                            <span class="tooltip-content">This message will be spoken to patients when they call. Keep it friendly and professional. If left blank, a default greeting will be used.</span>
                                        </span>
                                    </label>
                                    <textarea class="form-control" id="practiceGreeting" rows="3"
                                              placeholder="Hello! Thank you for calling Smith Family Medical Center. I'm your AI assistant and I'm here to help you schedule an appointment. How can I assist you today?"></textarea>
                                    <div class="form-help-text">This will be spoken to patients when they call (optional)</div>
                                </div>
                            </form>

                            <div class="validation-message" id="step1Validation"></div>
                        </div>

                        <!-- Step 2: Providers -->
                        <div class="wizard-step" data-step="2">
                            <h3 class="step-title">Provider Setup</h3>
                            <p class="step-description">Add the healthcare providers who will be available for appointments.</p>

                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <span class="fw-bold">Providers</span>
                                <button type="button" class="btn btn-primary btn-sm" id="addWizardProvider">
                                    <i class="fas fa-plus"></i> Add Provider
                                </button>
                            </div>

                            <div id="wizardProvidersList">
                                <!-- Provider items will be added here -->
                            </div>

                            <div class="alert alert-info mt-3">
                                <i class="fas fa-info-circle"></i>
                                <strong>Tip:</strong> Add at least one provider to enable appointment scheduling. You can always add more providers later.
                            </div>

                            <div class="validation-message" id="step2Validation"></div>
                        </div>

                        <!-- Step 3: Business Hours -->
                        <div class="wizard-step" data-step="3">
                            <h3 class="step-title">Business Hours</h3>
                            <p class="step-description">Set your practice's operating hours. The voice AI will only accept appointments during these times.</p>

                            <div class="quick-template-buttons">
                                <h6>Quick Templates:</h6>
                                <button type="button" class="btn btn-outline-primary btn-sm" onclick="wizard.applyHoursTemplate('standard')">
                                    Standard (9 AM - 5 PM, Mon-Fri)
                                </button>
                                <button type="button" class="btn btn-outline-primary btn-sm" onclick="wizard.applyHoursTemplate('extended')">
                                    Extended (8 AM - 6 PM, Mon-Fri)
                                </button>
                                <button type="button" class="btn btn-outline-primary btn-sm" onclick="wizard.applyHoursTemplate('weekend')">
                                    Include Weekends
                                </button>
                            </div>

                            <div id="wizardBusinessHours">
                                <!-- Business hours form will be populated here -->
                            </div>

                            <div class="validation-message" id="step3Validation"></div>
                        </div>

                        <!-- Step 4: Appointment Types -->
                        <div class="wizard-step" data-step="4">
                            <h3 class="step-title">Appointment Types</h3>
                            <p class="step-description">Define the types of appointments your practice offers and their typical durations.</p>

                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <span class="fw-bold">Appointment Types</span>
                                <button type="button" class="btn btn-primary btn-sm" id="addWizardAppointmentType">
                                    <i class="fas fa-plus"></i> Add Type
                                </button>
                            </div>

                            <div id="wizardAppointmentTypesList">
                                <!-- Appointment types will be added here -->
                            </div>

                            <div class="alert alert-info mt-3">
                                <i class="fas fa-info-circle"></i>
                                <strong>Tip:</strong> Common appointment types have been pre-configured for you. You can modify or add new types as needed.
                            </div>

                            <div class="validation-message" id="step4Validation"></div>
                        </div>
                    </div>

                    <div class="wizard-footer">
                        <div class="wizard-navigation">
                            <button type="button" class="btn btn-secondary" id="wizardPrevBtn" disabled>
                                <i class="fas fa-chevron-left"></i> Previous
                            </button>
                        </div>

                        <div class="save-resume-info">
                            <small><i class="fas fa-save"></i> Progress automatically saved</small>
                        </div>

                        <div class="wizard-navigation">
                            <button type="button" class="btn btn-primary" id="wizardNextBtn">
                                Next <i class="fas fa-chevron-right"></i>
                            </button>
                            <button type="button" class="btn btn-success d-none" id="wizardFinishBtn">
                                <i class="fas fa-check"></i> Complete Setup
                            </button>
                            <button type="button" class="btn btn-outline-secondary ms-2" id="wizardCloseBtn">
                                <i class="fas fa-times"></i> Cancel
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', wizardHTML);
    }

    attachEventListeners() {
        // Navigation buttons
        document.getElementById('wizardPrevBtn').addEventListener('click', () => this.previousStep());
        document.getElementById('wizardNextBtn').addEventListener('click', () => this.nextStep());
        document.getElementById('wizardFinishBtn').addEventListener('click', () => this.finishWizard());
        document.getElementById('wizardCloseBtn').addEventListener('click', () => this.closeWizard());

        // Show wizard button (in dashboard)
        const showWizardBtn = document.getElementById('showWizardBtn');
        if (showWizardBtn) {
            showWizardBtn.addEventListener('click', () => this.showWizard());
        }

        // Provider management in wizard
        document.getElementById('addWizardProvider').addEventListener('click', () => this.addWizardProvider());

        // Appointment type management in wizard
        document.getElementById('addWizardAppointmentType').addEventListener('click', () => this.addWizardAppointmentType());

        // Form change listeners for auto-save
        this.attachFormChangeListeners();

        // Close on overlay click
        document.getElementById('configurationWizardOverlay').addEventListener('click', (e) => {
            if (e.target.id === 'configurationWizardOverlay') {
                this.closeWizard();
            }
        });
    }

    attachFormChangeListeners() {
        const forms = ['practiceInfoForm'];
        forms.forEach(formId => {
            const form = document.getElementById(formId);
            if (form) {
                form.addEventListener('input', () => this.saveProgress());
                form.addEventListener('change', () => this.saveProgress());
            }
        });
    }

    showWizard() {
        this.isVisible = true;
        const overlay = document.getElementById('configurationWizardOverlay');
        overlay.classList.add('show');
        document.body.style.overflow = 'hidden';

        // Initialize business hours form
        this.initializeBusinessHoursForm();

        // Load default appointment types if none exist
        if (this.wizardData.appointmentTypes.length === 0) {
            this.loadDefaultAppointmentTypes();
        }

        this.updateWizardDisplay();
    }

    closeWizard() {
        this.isVisible = false;
        const overlay = document.getElementById('configurationWizardOverlay');
        overlay.classList.remove('show');
        document.body.style.overflow = '';
    }

    nextStep() {
        if (this.validateCurrentStep()) {
            this.saveProgress();
            if (this.currentStep < this.totalSteps) {
                this.currentStep++;
                this.updateWizardDisplay();
            }
        }
    }

    previousStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.updateWizardDisplay();
        }
    }

    updateWizardDisplay() {
        // Update progress steps
        document.querySelectorAll('.progress-step').forEach((step, index) => {
            const stepNumber = index + 1;
            step.classList.remove('current', 'completed');

            if (stepNumber < this.currentStep) {
                step.classList.add('completed');
                step.querySelector('.step-circle').innerHTML = '<i class="fas fa-check"></i>';
            } else if (stepNumber === this.currentStep) {
                step.classList.add('current');
                step.querySelector('.step-circle').innerHTML = stepNumber;
            } else {
                step.querySelector('.step-circle').innerHTML = stepNumber;
            }
        });

        // Update step content
        document.querySelectorAll('.wizard-step').forEach((step, index) => {
            const stepNumber = index + 1;
            step.classList.toggle('active', stepNumber === this.currentStep);
        });

        // Update navigation buttons
        const prevBtn = document.getElementById('wizardPrevBtn');
        const nextBtn = document.getElementById('wizardNextBtn');
        const finishBtn = document.getElementById('wizardFinishBtn');

        prevBtn.disabled = this.currentStep === 1;

        if (this.currentStep === this.totalSteps) {
            nextBtn.classList.add('d-none');
            finishBtn.classList.remove('d-none');
        } else {
            nextBtn.classList.remove('d-none');
            finishBtn.classList.add('d-none');
        }
    }

    validateCurrentStep() {
        let isValid = true;
        let validationMessage = '';

        switch (this.currentStep) {
            case 1:
                const requiredFields = ['practiceName', 'practicePhone', 'practiceAddress', 'practiceCity', 'practiceState', 'practiceZip'];
                const missingFields = requiredFields.filter(fieldId => {
                    const field = document.getElementById(fieldId);
                    return !field || !field.value.trim();
                });

                if (missingFields.length > 0) {
                    isValid = false;
                    validationMessage = 'Please fill in all required fields.';
                }
                break;

            case 2:
                if (this.wizardData.providers.length === 0) {
                    isValid = false;
                    validationMessage = 'Please add at least one provider.';
                }
                break;

            case 3:
                // Validate that at least one day has hours set
                const hasAnyHours = Object.values(this.wizardData.hours).some(day =>
                    day && day.isOpen && day.start && day.end
                );
                if (!hasAnyHours) {
                    isValid = false;
                    validationMessage = 'Please set business hours for at least one day.';
                }
                break;

            case 4:
                if (this.wizardData.appointmentTypes.length === 0) {
                    isValid = false;
                    validationMessage = 'Please add at least one appointment type.';
                }
                break;
        }

        this.showValidationMessage(this.currentStep, isValid, validationMessage);
        return isValid;
    }

    showValidationMessage(step, isValid, message) {
        const validationEl = document.getElementById(`step${step}Validation`);
        if (validationEl) {
            if (message) {
                validationEl.textContent = message;
                validationEl.className = `validation-message ${isValid ? 'success' : 'error'}`;
                validationEl.style.display = 'block';
            } else {
                validationEl.style.display = 'none';
            }
        }
    }

    saveProgress() {
        // Collect current form data
        this.collectFormData();

        // Save to localStorage
        const progressData = {
            currentStep: this.currentStep,
            wizardData: this.wizardData,
            timestamp: Date.now()
        };
        localStorage.setItem(this.progressKey, JSON.stringify(progressData));
    }

    loadSavedProgress() {
        const saved = localStorage.getItem(this.progressKey);
        if (saved) {
            try {
                const progressData = JSON.parse(saved);
                this.currentStep = progressData.currentStep || 1;
                this.wizardData = progressData.wizardData || this.wizardData;

                // Populate form fields
                this.populateFormFields();
            } catch (e) {
                console.error('Error loading saved progress:', e);
            }
        }
    }

    collectFormData() {
        // Step 1: Practice Information
        const practiceFields = ['practiceName', 'practicePhone', 'practiceAddress', 'practiceCity', 'practiceState', 'practiceZip', 'practiceGreeting'];
        practiceFields.forEach(fieldId => {
            const field = document.getElementById(fieldId);
            if (field) {
                this.wizardData.practice[fieldId.replace('practice', '').toLowerCase()] = field.value;
            }
        });

        // Step 3: Business Hours
        this.collectBusinessHoursData();
    }

    populateFormFields() {
        // Step 1: Practice Information
        Object.entries(this.wizardData.practice).forEach(([key, value]) => {
            const fieldId = 'practice' + key.charAt(0).toUpperCase() + key.slice(1);
            const field = document.getElementById(fieldId);
            if (field) {
                field.value = value || '';
            }
        });

        // Step 2: Providers
        this.updateWizardProvidersList();

        // Step 4: Appointment Types
        this.updateWizardAppointmentTypesList();
    }

    addWizardProvider() {
        const provider = {
            id: this.generateId(),
            name: '',
            specialization: '',
            schedule: {}
        };

        this.wizardData.providers.push(provider);
        this.updateWizardProvidersList();
    }

    updateWizardProvidersList() {
        const container = document.getElementById('wizardProvidersList');
        container.innerHTML = '';

        this.wizardData.providers.forEach((provider, index) => {
            const providerHtml = `
                <div class="card mb-2">
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-5">
                                <input type="text" class="form-control" placeholder="Provider Name"
                                       value="${provider.name}" data-provider-index="${index}" data-field="name">
                            </div>
                            <div class="col-md-5">
                                <input type="text" class="form-control" placeholder="Specialization"
                                       value="${provider.specialization}" data-provider-index="${index}" data-field="specialization">
                            </div>
                            <div class="col-md-2">
                                <button type="button" class="btn btn-outline-danger btn-sm w-100"
                                        onclick="wizard.removeWizardProvider(${index})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', providerHtml);
        });

        // Attach event listeners for provider inputs
        container.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.target.dataset.providerIndex);
                const field = e.target.dataset.field;
                this.wizardData.providers[index][field] = e.target.value;
                this.saveProgress();
            });
        });
    }

    removeWizardProvider(index) {
        this.wizardData.providers.splice(index, 1);
        this.updateWizardProvidersList();
        this.saveProgress();
    }

    initializeBusinessHoursForm() {
        const container = document.getElementById('wizardBusinessHours');
        const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
        const dayLabels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

        let hoursHtml = '<div class="schedule-container">';

        days.forEach((day, index) => {
            const dayData = this.wizardData.hours[day] || { isOpen: false, start: '09:00', end: '17:00' };

            hoursHtml += `
                <div class="schedule-grid mb-2">
                    <label class="form-label">${dayLabels[index]}</label>
                    <div class="form-check">
                        <input class="form-check-input day-toggle" type="checkbox"
                               id="wizard_${day}_open" ${dayData.isOpen ? 'checked' : ''} data-day="${day}">
                        <label class="form-check-label" for="wizard_${day}_open">Open</label>
                    </div>
                    <div class="d-flex gap-2">
                        <input type="time" class="form-control time-input" id="wizard_${day}_start"
                               value="${dayData.start}" ${!dayData.isOpen ? 'disabled' : ''} data-day="${day}" data-field="start">
                        <span class="align-self-center">to</span>
                        <input type="time" class="form-control time-input" id="wizard_${day}_end"
                               value="${dayData.end}" ${!dayData.isOpen ? 'disabled' : ''} data-day="${day}" data-field="end">
                    </div>
                </div>
            `;
        });

        hoursHtml += '</div>';
        container.innerHTML = hoursHtml;

        // Attach event listeners
        container.querySelectorAll('.day-toggle').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const day = e.target.dataset.day;
                const isOpen = e.target.checked;

                this.wizardData.hours[day] = this.wizardData.hours[day] || {};
                this.wizardData.hours[day].isOpen = isOpen;

                // Enable/disable time inputs
                const startInput = document.getElementById(`wizard_${day}_start`);
                const endInput = document.getElementById(`wizard_${day}_end`);
                startInput.disabled = !isOpen;
                endInput.disabled = !isOpen;

                this.saveProgress();
            });
        });

        container.querySelectorAll('.time-input').forEach(input => {
            input.addEventListener('change', (e) => {
                const day = e.target.dataset.day;
                const field = e.target.dataset.field;

                this.wizardData.hours[day] = this.wizardData.hours[day] || {};
                this.wizardData.hours[day][field] = e.target.value;

                this.saveProgress();
            });
        });
    }

    collectBusinessHoursData() {
        const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

        days.forEach(day => {
            const checkbox = document.getElementById(`wizard_${day}_open`);
            const startInput = document.getElementById(`wizard_${day}_start`);
            const endInput = document.getElementById(`wizard_${day}_end`);

            if (checkbox && startInput && endInput) {
                this.wizardData.hours[day] = {
                    isOpen: checkbox.checked,
                    start: startInput.value,
                    end: endInput.value
                };
            }
        });
    }

    applyHoursTemplate(template) {
        const templates = {
            standard: {
                monday: { isOpen: true, start: '09:00', end: '17:00' },
                tuesday: { isOpen: true, start: '09:00', end: '17:00' },
                wednesday: { isOpen: true, start: '09:00', end: '17:00' },
                thursday: { isOpen: true, start: '09:00', end: '17:00' },
                friday: { isOpen: true, start: '09:00', end: '17:00' },
                saturday: { isOpen: false, start: '09:00', end: '17:00' },
                sunday: { isOpen: false, start: '09:00', end: '17:00' }
            },
            extended: {
                monday: { isOpen: true, start: '08:00', end: '18:00' },
                tuesday: { isOpen: true, start: '08:00', end: '18:00' },
                wednesday: { isOpen: true, start: '08:00', end: '18:00' },
                thursday: { isOpen: true, start: '08:00', end: '18:00' },
                friday: { isOpen: true, start: '08:00', end: '18:00' },
                saturday: { isOpen: false, start: '09:00', end: '17:00' },
                sunday: { isOpen: false, start: '09:00', end: '17:00' }
            },
            weekend: {
                monday: { isOpen: true, start: '09:00', end: '17:00' },
                tuesday: { isOpen: true, start: '09:00', end: '17:00' },
                wednesday: { isOpen: true, start: '09:00', end: '17:00' },
                thursday: { isOpen: true, start: '09:00', end: '17:00' },
                friday: { isOpen: true, start: '09:00', end: '17:00' },
                saturday: { isOpen: true, start: '09:00', end: '15:00' },
                sunday: { isOpen: true, start: '10:00', end: '14:00' }
            }
        };

        this.wizardData.hours = templates[template] || templates.standard;
        this.initializeBusinessHoursForm();
        this.saveProgress();
    }

    loadDefaultAppointmentTypes() {
        this.wizardData.appointmentTypes = [
            {
                id: this.generateId(),
                name: 'Consultation',
                duration: 30,
                description: 'General consultation appointment'
            },
            {
                id: this.generateId(),
                name: 'Follow-up',
                duration: 20,
                description: 'Follow-up appointment for existing patients'
            },
            {
                id: this.generateId(),
                name: 'New Patient',
                duration: 45,
                description: 'Comprehensive appointment for new patients'
            }
        ];
        this.updateWizardAppointmentTypesList();
    }

    addWizardAppointmentType() {
        const appointmentType = {
            id: this.generateId(),
            name: '',
            duration: 30,
            description: ''
        };

        this.wizardData.appointmentTypes.push(appointmentType);
        this.updateWizardAppointmentTypesList();
    }

    updateWizardAppointmentTypesList() {
        const container = document.getElementById('wizardAppointmentTypesList');
        container.innerHTML = '';

        this.wizardData.appointmentTypes.forEach((type, index) => {
            const typeHtml = `
                <div class="card mb-2">
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-4">
                                <input type="text" class="form-control" placeholder="Appointment Type Name"
                                       value="${type.name}" data-type-index="${index}" data-field="name">
                            </div>
                            <div class="col-md-2">
                                <div class="input-group">
                                    <input type="number" class="form-control" placeholder="Duration" min="5" max="480"
                                           value="${type.duration}" data-type-index="${index}" data-field="duration">
                                    <span class="input-group-text">min</span>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <input type="text" class="form-control" placeholder="Description"
                                       value="${type.description}" data-type-index="${index}" data-field="description">
                            </div>
                            <div class="col-md-2">
                                <button type="button" class="btn btn-outline-danger btn-sm w-100"
                                        onclick="wizard.removeWizardAppointmentType(${index})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', typeHtml);
        });

        // Attach event listeners for appointment type inputs
        container.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.target.dataset.typeIndex);
                const field = e.target.dataset.field;
                let value = e.target.value;

                if (field === 'duration') {
                    value = parseInt(value) || 30;
                }

                this.wizardData.appointmentTypes[index][field] = value;
                this.saveProgress();
            });
        });
    }

    removeWizardAppointmentType(index) {
        this.wizardData.appointmentTypes.splice(index, 1);
        this.updateWizardAppointmentTypesList();
        this.saveProgress();
    }

    async finishWizard() {
        if (!this.validateCurrentStep()) {
            return;
        }

        try {
            // Collect all form data
            this.collectFormData();

            // Transform wizard data to configuration format
            const configData = this.transformWizardDataToConfig();

            // Save configuration
            const response = await fetch('/api/v1/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData)
            });

            if (response.ok) {
                // Clear saved progress
                localStorage.removeItem(this.progressKey);

                // Show success message
                this.showSuccessMessage();

                // Close wizard and refresh dashboard
                setTimeout(() => {
                    this.closeWizard();
                    if (window.configManager) {
                        window.configManager.loadConfiguration();
                    }
                }, 2000);
            } else {
                throw new Error('Failed to save configuration');
            }
        } catch (error) {
            console.error('Error completing wizard:', error);
            this.showValidationMessage(4, false, 'Failed to save configuration. Please try again.');
        }
    }

    transformWizardDataToConfig() {
        return {
            practice_information: {
                full_name: this.wizardData.practice.name || '',
                address: {
                    street: this.wizardData.practice.address || '',
                    city: this.wizardData.practice.city || '',
                    state: this.wizardData.practice.state || '',
                    zip: this.wizardData.practice.zip || ''
                },
                phone: this.wizardData.practice.phone || '',
                greeting_customization: {
                    custom_message: this.wizardData.practice.greeting || ''
                }
            },
            providers: this.wizardData.providers.filter(p => p.name.trim()),
            operational_hours: this.wizardData.hours,
            appointment_types: this.wizardData.appointmentTypes.filter(t => t.name.trim())
        };
    }

    showSuccessMessage() {
        const wizardContent = document.querySelector('.wizard-content');
        wizardContent.innerHTML = `
            <div class="text-center py-5">
                <div class="mb-4">
                    <i class="fas fa-check-circle text-success" style="font-size: 4rem;"></i>
                </div>
                <h3 class="text-success mb-3">Setup Complete!</h3>
                <p class="lead">Your practice configuration has been saved successfully.</p>
                <p>The voice AI system is now ready to handle patient calls and schedule appointments.</p>
            </div>
        `;
    }

    generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    }
}

// Initialize wizard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.wizard = new ConfigurationWizard();
});
