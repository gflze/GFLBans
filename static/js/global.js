//Request helper function

async function gbRequest(method='GET', url='', data={}, send_token=false) {
    let q = {
        method: method,
        mode: 'cors',
        cache: 'no-cache',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json'
        },
        redirect: 'follow'
    };

    if (data != null && (method !== 'GET' && method !== 'HEAD')) {
        q.body = JSON.stringify(data);
    }

    if (send_token) {
        q['headers']['X-CSRF-TOKEN'] = getMeta('csrf_token');
    }

    return await fetch(url, q);
}

$(document).ready(function () {
    //Toggle the burger for mobile mode
   $(".navbar-burger").click(function () {
       $(".navbar-burger").toggleClass("is-active");
       $(".navbar-menu").toggleClass("is-active");
   });

   //Switch between light and dark mode
   $("#dark-mode-toggle").click(function () {

      gbRequest('GET', '/toggle_theme').then(resp => {
         if (resp.ok) {
             location.reload();
         } else {
             throw 'Received a Non-OK response from the server';
         }
      }).catch(function (error) {
          console.log(error);
          showError();
      });
   });

    $(".modal-close").click(function () {
        closeModals();
    });

    $(".modal-background").click(function () {
        if (this.hasAttribute('no-click')) {
            return;
        }
        closeModals();
    });
});

function closeModals() {
    $('.modal').removeClass('is-active')
    $('#htmlRoot').removeClass('is-clipped')
}

//Utility function to get a meta attribute
function getMeta(metaName) {
  const metas = document.getElementsByTagName('meta');

  for (let i = 0; i < metas.length; i++) {
    if (metas[i].getAttribute('name') === metaName) {
      return metas[i].getAttribute('content');
    }
  }

  return '';
}

const defaultError = 'An error occurred while loading this page. Try again in a few minutes or contact the host if the problem persists.';

function showError(error_message=defaultError) {
    closeModals();

    //Setup and show the error modal
    $('#errorMessage').text(error_message);
    $('#errorModal').addClass('is-active');

    $('#htmlRoot').addClass('is-clipped');
}

function getProfileUrl(ply) {
    switch (ply['gs_service']) {
        case "steam": return "//steamcommunity.com/profiles/" + ply['gs_id'];
        default: return null;
    }
}

function openLinkInNewTab(url) {
    window.open(url, '_blank');
}

//Cache admin data to speed up loading and reduce load on the server
let admin_cache = new Map();

async function get_admin(admin_id) {
    if (admin_cache.has(admin_id)) {
        return admin_cache.get(admin_id);
    }

    let resp = await gbRequest('GET', '/api/gs/admininfo?ips_id=' + admin_id, null)

    if (!resp.ok) {
        throw 'Received Not-OK from API';
    }

    let data = await resp.json()

    admin_cache.set(admin_id, data);

    return data;
}

function insertParam(key, value) {
    let url = new URL(document.URL);

    let sp = url.searchParams;

    sp.set(key, value);

    document.location.search = sp.toString();
}

async function uploadAttachment(infraction, filename, fi, private=false) {
    let hdrs = {'Content-Type': "application/octet-stream", 'X-CSRF-TOKEN': getMeta('csrf_token')};

    if (private) {
        hdrs['X-Set-Private'] = "true"
    }

    return await fetch('/api/infractions/' + infraction + '/attachment/' + filename, {
        method: 'POST',
        headers: hdrs,
        body: fi,
        mode: 'cors',
        cache: 'no-cache',
        credentials: 'same-origin',
        redirect: 'follow'
    })
}

document.addEventListener('load', function () {
    $('.set-default-on-error').on("error", function () {
        this.setAttribute('src', '/static/images/fallback_av.png');
        this.classList.remove('set-default-on-error');
    })
});

function genericError(err) {
    console.log(err);
    showError();
}