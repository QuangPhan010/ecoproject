/* ================= CSRF TOKEN ================= */
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let cookie of cookies) {
      cookie = cookie.trim();
      if (cookie.startsWith(name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
const csrftoken = getCookie("csrftoken");

/* ================= SCROLL ================= */
window.scrollToSection = function (id) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

/* ================= COLOR SELECT ================= */
document.querySelectorAll(".color-dot").forEach(dot => {
  dot.addEventListener("click", () => {
    document.querySelectorAll(".color-dot").forEach(d => d.classList.remove("active"));
    dot.classList.add("active");
  });
});

/* ================= STAR RATING ================= */
const stars = document.querySelectorAll(".star-input");
const ratingInput = document.getElementById("rating-value");

function highlightStars(value) {
  stars.forEach(star => {
    star.classList.toggle("active", Number(star.dataset.value) <= value);
  });
}

if (ratingInput) {
  highlightStars(ratingInput.value || 0);
}

stars.forEach(star => {
  star.addEventListener("click", () => {
    const value = star.dataset.value;
    ratingInput.value = value;
    highlightStars(value);
  });
});

/* ================= ADD REVIEW ================= */
const reviewForm = document.getElementById("review-form");
if (reviewForm) {
  reviewForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const addReviewUrl = this.dataset.addUrl;
    const formData = new FormData(this);

    fetch(addReviewUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrftoken },
      body: formData,
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          alert(data.error);
          return;
        }
        location.reload();
      })
      .catch(err => {
        console.error(err);
        alert("Gửi đánh giá thất bại");
      });
  });
}

/* ================= REPLY REVIEW ================= */
document.querySelectorAll(".reply-form").forEach(form => {
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const addReviewUrl = this.dataset.addUrl;
    const content = this.querySelector("textarea").value.trim();
    const parentId = this.dataset.parent;
    if (!content) return;

    fetch(addReviewUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrftoken,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ content: content, parent_id: parentId }),
    })
      .then(res => res.json())
      .then(() => location.reload())
      .catch(err => console.error(err));
  });
});

/* ================= DELETE REVIEW ================= */
window.deleteReview = function (url) {
  if (!confirm("Bạn chắc chắn muốn xóa đánh giá này?")) return;

  fetch(url, {
    method: "POST",
    headers: { "X-CSRFToken": csrftoken },
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        document.getElementById(`review-${data.review_id}`)?.remove();
      } else {
        alert(data.error || "Không thể xóa đánh giá");
      }
    })
    .catch(err => console.error(err));
}

/* ================= EDIT REVIEW ================= */
document.querySelectorAll('.js-edit-review').forEach(button => {
    button.addEventListener('click', () => {
        const url = button.dataset.url;
        const rating = button.dataset.rating;
        const content = button.dataset.content;

        openEdit(button, url, rating, content);
    });
});

function openEdit(button, url, rating, content) {
    const reviewCard = button.closest('.review-card');
    const reviewContentP = reviewCard.querySelector('.review-content');
    const actionsDiv = button.closest('.float-end');

    const editForm = document.createElement('form');
    editForm.classList.add('edit-form');
    editForm.innerHTML = `
        <div class="rating-input mb-2">
            <input type="hidden" name="rating" value="${rating}" />
            <span class="star-input" data-value="1">★</span>
            <span class="star-input" data-value="2">★</span>
            <span class="star-input" data-value="3">★</span>
            <span class="star-input" data-value="4">★</span>
            <span class="star-input" data-value="5">★</span>
        </div>
        <textarea class="form-control" rows="3">${content}</textarea>
        <div class="mt-2">
            <button type="submit" class="btn btn-primary btn-sm">Lưu</button>
            <button type="button" class="btn btn-secondary btn-sm cancel-edit">Hủy</button>
        </div>
    `;

    reviewContentP.style.display = 'none';
    actionsDiv.style.display = 'none';
    
    reviewCard.appendChild(editForm);

    const ratingStars = editForm.querySelectorAll('.star-input');
    const ratingInput = editForm.querySelector('input[name="rating"]');

    function highlightStars(value) {
        ratingStars.forEach(star => {
            star.classList.toggle('active', star.dataset.value <= value);
        });
    }
    highlightStars(rating);

    ratingStars.forEach(star => {
        star.addEventListener('click', () => {
            const value = star.dataset.value;
            ratingInput.value = value;
            highlightStars(value);
        });
    });


    editForm.querySelector('.cancel-edit').addEventListener('click', () => {
        reviewContentP.style.display = 'block';
        actionsDiv.style.display = 'block';
        editForm.remove();
    });

    editForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const newContent = editForm.querySelector('textarea').value;
        const newRating = ratingInput.value;

        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                rating: newRating,
                content: newContent
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
                return;
            }
            reviewContentP.textContent = data.content;
            
            const starsSpan = reviewCard.querySelector('.star');
            let starsHTML = '';
            for (let i = 1; i <= 5; i++) {
                starsHTML += i <= data.rating ? '★' : '☆';
            }
            starsSpan.innerHTML = starsHTML;

            button.dataset.rating = data.rating;
            button.dataset.content = data.content;

            reviewContentP.style.display = 'block';
            actionsDiv.style.display = 'block';
            editForm.remove();
        })
        .catch(err => console.error(err));
    });
}


/* ================= LIKE / DISLIKE ================= */
document.querySelectorAll('.js-react-btn').forEach(button => {
    button.addEventListener('click', () => {
        const reviewId = button.dataset.reviewId;
        const isLike = button.dataset.isLike;
        reactReview(button, reviewId, isLike);
    });
});

function reactReview(button, reviewId, isLike) {
    const reactUrl = document.getElementById('review-list').dataset.reactUrl;
    fetch(reactUrl, {
    method: "POST",
    headers: {
      "X-CSRFToken": csrftoken,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ review_id: reviewId, is_like: isLike }),
    })
    .then(res => res.json())
    .then(data => {
        const reviewCard = button.closest('.review-card');
        reviewCard.querySelector('.likes-count').textContent = data.likes;
        reviewCard.querySelector('.dislikes-count').textContent = data.dislikes;
    })
    .catch(err => console.error(err));
}

/* ================= ADD TO CART ================= */
document.querySelector('.js-add-to-cart')?.addEventListener('click', (e) => {
    e.preventDefault();
    const button = e.target;
    const url = button.dataset.url;
    
    addToCart(url);
});

function addToCart(url) {
    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
        },
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            alert('Đã thêm vào giỏ hàng!');
            updateCartIcon(Object.keys(data.cart).length);
        }
    })
    .catch(err => console.error(err));
}

function updateCartIcon(count) {
    const cartIcon = document.getElementById('cart-count');
    if (cartIcon) {
        cartIcon.textContent = count;
    }
}