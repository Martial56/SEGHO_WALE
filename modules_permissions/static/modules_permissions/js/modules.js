// modules_permissions/static/modules_permissions/js/modules.js

document.addEventListener('DOMContentLoaded', function() {
    // Initialize module management functionalities
    const moduleList = document.getElementById('module-list');
    const groupSelect = document.getElementById('group-select');

    // Function to filter modules based on selected group
    function filterModulesByGroup() {
        const selectedGroup = groupSelect.value;
        const modules = moduleList.getElementsByClassName('module-item');

        for (let module of modules) {
            if (module.dataset.group === selectedGroup || selectedGroup === 'all') {
                module.style.display = 'block';
            } else {
                module.style.display = 'none';
            }
        }
    }

    // Event listener for group selection change
    groupSelect.addEventListener('change', filterModulesByGroup);

    // Initial filter on page load
    filterModulesByGroup();
});