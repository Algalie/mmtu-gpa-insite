// MMTU GPA Insite - Frontend JavaScript

// Global variable for number of modules
let numModules = 5;

// Render module rows function
function renderModuleRows() {
    const container = document.getElementById('modulesContainer');
    
    // Get numModules from global or from script tag
    if (typeof window.numModules !== 'undefined') {
        numModules = window.numModules;
    }
    
    container.innerHTML = '';
    
    for (let i = 1; i <= numModules; i++) {
        const moduleRow = document.createElement('div');
        moduleRow.className = 'module-row';
        moduleRow.innerHTML = `
            <div class="form-group">
                <label for="module_${i}_label">Module ${i}</label>
                <input type="text" 
                       class="module-code" 
                       placeholder="Module code (optional)" 
                       id="module_${i}_code"
                       name="module_${i}_code">
            </div>
            
            <div class="form-group">
                <label for="module_${i}_grade">Grade</label>
                <select class="grade-select" 
                        id="module_${i}_grade" 
                        name="module_${i}_grade" 
                        required>
                    <option value="">Select Grade</option>
                    <option value="A">A (5.0 points)</option>
                    <option value="B">B (4.0 points)</option>
                    <option value="C">C (3.0 points)</option>
                    <option value="D">D (2.0 points)</option>
                    <option value="E">E (1.0 points)</option>
                    <option value="F">F (0.0 points)</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>Credits</label>
                <input type="text" value="3" disabled class="credit-display">
                <small>Fixed to 3 credits per module</small>
            </div>
            
            <div class="form-group reference-toggle">
                <input type="checkbox" 
                       class="reference-checkbox" 
                       id="module_${i}_reference" 
                       name="module_${i}_reference">
                <label for="module_${i}_reference">Mark as Reference</label>
                <small>Steps grade down by one level</small>
            </div>
        `;
        
        container.appendChild(moduleRow);
    }
    
    console.log(`Rendered ${numModules} module rows`);
}

// Setup event listeners
function setupEventListeners() {
    // Check for E/F grades on any grade change
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('grade-select')) {
            console.log('Grade changed:', e.target.value);
            checkForBlockingGrades();
            highlightChangedRow(e.target);
        }
        
        if (e.target.classList.contains('reference-checkbox')) {
            console.log('Reference checkbox toggled:', e.target.checked);
            highlightChangedRow(e.target);
        }
    });
    
    // Calculate button handler
    const calculateBtn = document.getElementById('calculateBtn');
    if (calculateBtn) {
        calculateBtn.addEventListener('click', calculateGPA);
        console.log('Calculate button event listener added');
    }
    
    // Form reset handler
    const resetBtn = document.querySelector('button[type="reset"]');
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            setTimeout(checkForBlockingGrades, 100);
        });
    }
}

// Highlight row when changed
function highlightChangedRow(element) {
    const row = element.closest('.module-row');
    if (row) {
        row.style.backgroundColor = '#f0fff4';
        setTimeout(() => {
            row.style.backgroundColor = '';
        }, 1000);
    }
}

// Check for blocking grades (E or F)
function checkForBlockingGrades() {
    const gradeSelects = document.querySelectorAll('.grade-select');
    const blockedMessage = document.getElementById('blockedMessage');
    const calculateBtn = document.getElementById('calculateBtn');
    
    let hasEF = false;
    
    gradeSelects.forEach(select => {
        if (select.value === 'E' || select.value === 'F') {
            hasEF = true;
            console.log('Found E/F grade:', select.value);
        }
    });
    
    if (hasEF) {
        blockedMessage.style.display = 'block';
        if (calculateBtn) {
            calculateBtn.disabled = true;
            calculateBtn.style.opacity = '0.5';
            calculateBtn.style.cursor = 'not-allowed';
        }
        console.log('Calculation blocked due to E/F grades');
    } else {
        blockedMessage.style.display = 'none';
        if (calculateBtn) {
            calculateBtn.disabled = false;
            calculateBtn.style.opacity = '1';
            calculateBtn.style.cursor = 'pointer';
        }
    }
}

// Calculate GPA function
function calculateGPA() {
    console.log('Calculate GPA function called');
    
    const modules = collectModuleData();
    console.log('Collected modules:', modules);
    
    // Validate all grades are selected
    let allGradesSelected = true;
    const emptyGrades = [];
    
    modules.forEach((module, index) => {
        if (!module.grade) {
            allGradesSelected = false;
            emptyGrades.push(index + 1);
        }
    });
    
    if (!allGradesSelected) {
        alert(`Please select grades for all modules. Missing grades in: Module ${emptyGrades.join(', Module ')}`);
        return;
    }
    
    const calculateBtn = document.getElementById('calculateBtn');
    const originalText = calculateBtn.textContent;
    
    calculateBtn.disabled = true;
    calculateBtn.textContent = 'Calculating...';
    calculateBtn.style.opacity = '0.7';
    
    // Show loading state
    document.body.style.cursor = 'wait';
    
    console.log('Sending calculation request...');
    
    fetch('/calculate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ modules: modules })
    })
    .then(response => {
        console.log('Response status:', response.status);
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.message || 'Calculation failed');
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Calculation response:', data);
        if (data.blocked) {
            alert(data.message);
        } else {
            // Success - redirect to result page
            console.log('Calculation successful, redirecting to result page');
            window.location.href = '/result';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred during calculation: ' + error.message);
    })
    .finally(() => {
        calculateBtn.disabled = false;
        calculateBtn.textContent = originalText;
        calculateBtn.style.opacity = '1';
        document.body.style.cursor = 'default';
    });
}

// Collect module data from form
function collectModuleData() {
    const modules = [];
    const moduleRows = document.querySelectorAll('.module-row');
    
    console.log(`Found ${moduleRows.length} module rows`);
    
    moduleRows.forEach((row, index) => {
        const codeInput = row.querySelector('.module-code');
        const gradeSelect = row.querySelector('.grade-select');
        const referenceCheckbox = row.querySelector('.reference-checkbox');
        
        const moduleData = {
            label: `Module ${index + 1}`,
            code: codeInput ? codeInput.value.trim() : '',
            grade: gradeSelect ? gradeSelect.value : '',
            reference: referenceCheckbox ? referenceCheckbox.checked : false,
            credit: 3
        };
        
        console.log(`Module ${index + 1}:`, moduleData);
        modules.push(moduleData);
    });
    
    return modules;
}

// Global functions for result page
function openSaveModal() {
    document.getElementById('saveModal').style.display = 'flex';
    document.getElementById('title').focus();
}

function closeSaveModal() {
    document.getElementById('saveModal').style.display = 'none';
    document.getElementById('saveForm').reset();
}

function saveResult(event) {
    event.preventDefault();
    
    const title = document.getElementById('title').value.trim();
    if (!title) {
        alert('Please enter a title for your result');
        return;
    }
    
    const form = document.getElementById('saveForm');
    const formData = new FormData(form);
    const saveButton = form.querySelector('button[type="submit"]');
    const originalText = saveButton.textContent;
    
    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';
    
    fetch('/save-result', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(data.message);
            window.location.href = '/saved-records';
        } else {
            alert(data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while saving: ' + error.message);
    })
    .finally(() => {
        saveButton.disabled = false;
        saveButton.textContent = originalText;
    });
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page loaded, initializing modules input...');
    
    // Close modal when clicking outside
    const modal = document.getElementById('saveModal');
    if (modal) {
        modal.addEventListener('click', function(event) {
            if (event.target === this) {
                closeSaveModal();
            }
        });
    }
    
    // Add some animation effects
    const cards = document.querySelectorAll('.dashboard-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
});