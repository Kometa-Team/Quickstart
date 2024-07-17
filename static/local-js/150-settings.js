/* global $, alert */

document.addEventListener('DOMContentLoaded', function () {
  const saveSyncChangesButton = document.getElementById('saveSyncChangesButton')
  const saveExcludeChangesButton = document.getElementById('saveExcludeChangesButton')

  saveSyncChangesButton.addEventListener('click', function () {
    const selectedUsers = []
    const checkboxes = document.querySelectorAll('#syncUserListForm input[type="checkbox"]:checked')

    const allSelected = document.getElementById('sync_all_users').checked

    if (allSelected) {
      selectedUsers.push('all')
    } else {
      checkboxes.forEach((checkbox) => {
        if (checkbox.value !== 'all') {
          selectedUsers.push(checkbox.value)
        }
      })
    }

    const csvUsers = selectedUsers.join(', ')
    document.getElementById('playlist_sync_to_users').value = csvUsers
    $('#syncUsersModal').modal('hide')
  })

  saveExcludeChangesButton.addEventListener('click', function () {
    const selectedUsers = []
    const checkboxes = document.querySelectorAll('#excludeUserListForm input[type="checkbox"]:checked')

    checkboxes.forEach((checkbox) => {
      selectedUsers.push(checkbox.value)
    })

    const csvUsers = selectedUsers.join(', ')
    document.getElementById('playlist_exclude_users').value = csvUsers
    $('#excludeUsersModal').modal('hide')
  })

  const syncAllUsersCheckbox = document.getElementById('sync_all_users')
  syncAllUsersCheckbox.addEventListener('change', function () {
    if (this.checked) {
      const checkboxes = document.querySelectorAll('#syncUserListForm input[type="checkbox"]:not(#sync_all_users)')
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false
      })
    }
  })

  const syncUserCheckboxes = document.querySelectorAll('#syncUserListForm input[type="checkbox"]:not(#sync_all_users)')
  syncUserCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener('change', function () {
      if (this.checked) {
        syncAllUsersCheckbox.checked = false
      }
    })
  })
})

$(document).ready(function () {
  const isValidated = document.getElementById('settings_validated').value.toLowerCase()
  console.log('Validated: ' + isValidated)
})

function validatePath (input) {
  // Regular expression for validating paths
  // Accepts paths like:
  // Windows absolute: C:\Folder\file.txt, \\server\share\file.txt
  // Windows relative: folder\subfolder\file.txt
  // Unix absolute: /path/to/file.txt
  // Unix relative: ./relative/path/file.txt, config/assets
  const pathRegex = /^(?:[a-zA-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*|\\{2}[^\\/:*?"<>|\r\n]+(?:\\[^\\/:*?"<>|\r\n]+)*|(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+|\/(?:[^\/]+\/)*[^\/]*|\.{1,2}(?:\/[^\/]*)*|(?:[^\/]+\/)*[^\/]*)$/  // eslint-disable-line
  return pathRegex.test(input)
}

function validateCSVList (input) {
  // If the input is null or empty, return true (consider it valid)
  if (!input) {
    return true
  }

  // Regular expression for validating CSV lists
  // Accepts lists like: item1, item2, item3
  // Each item can be alphanumeric and can include spaces, hyphens, underscores, and dots
  const csvRegex = /^(\s*[a-zA-Z0-9-_.]+\s*)(,\s*[a-zA-Z0-9-_.]+\s*)*$/
  return csvRegex.test(input)
}

/* eslint-disable no-unused-vars */
function validateForm () {
  const assetDirectoryInput = document.getElementById('asset_directory').value.trim()
  if (!validatePath(assetDirectoryInput)) {
    alert('Please enter a valid asset directory path.')
    return false // Prevent form submission
  }

  // Validate CSV list fields
  const csvFields = ['playlist_sync_to_users', 'playlist_exclude_users']
  for (const fieldId of csvFields) {
    const fieldValue = document.getElementById(fieldId).value.trim()
    if (!validateCSVList(fieldValue)) {
      alert(`Please enter a valid CSV list for ${fieldId.replace('_', ' ')}.`)
      return false // Prevent form submission
    }
  }

  // Validate ignore_ids to be numeric
  const ignoreIds = document.getElementById('ignore_ids').value.trim()
  if (ignoreIds && !validateNumericCSV(ignoreIds)) {
    alert('Please enter a valid CSV list of numeric IDs for ignore_ids.')
    return false // Prevent form submission
  }

  // Validate ignore_imdb_ids to start with tt followed by numbers
  const ignoreImdbIds = document.getElementById('ignore_imdb_ids').value.trim()
  if (ignoreImdbIds && !validateIMDBCSV(ignoreImdbIds)) {
    alert('Please enter a valid CSV list of IMDb IDs for ignore_imdb_ids (starting with tt followed by numbers).')
    return false // Prevent form submission
  }

  // Validate custom_repo to be a valid URL
  const customRepo = document.getElementById('custom_repo').value.trim()
  if (customRepo && customRepo.toLowerCase() !== 'none' && !validateURL(customRepo)) {
    alert('Please enter a valid URL for custom_repo.')
    return false // Prevent form submission
  }

  // Additional form validation logic can go here if needed
  return true // Allow form submission
}

function validateNumericCSV (input) {
  const numericCSVRegex = /^(\s*\d+\s*)(,\s*\d+\s*)*$/
  return numericCSVRegex.test(input)
}

function validateIMDBCSV (input) {
  const imdbCSVRegex = /^(\s*tt\d+\s*)(,\s*tt\d+\s*)*$/
  return imdbCSVRegex.test(input)
}

function validateURL (input) {
  const urlRegex = /^(https?|ftp):\/\/[^\s/$.?#].[^\s]*$/i
  return urlRegex.test(input)
}
